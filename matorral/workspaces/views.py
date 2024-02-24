import ujson

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from ..utils import get_clean_next_url
from .models import Workspace
from .tasks import duplicate_workspaces, remove_workspaces


@method_decorator(login_required, name='dispatch')
class WorkspaceDetailView(DetailView):

    model = Workspace

    def get_children(self):
        return self.get_object().members.order_by('username')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['objects_by_group'] = [(None, self.get_children())]
        context['current_workspace'] = self.kwargs['workspace']
        return context

    def post(self, *args, **kwargs):
        params = ujson.loads(self.request.body)
        url = self.request.get_full_path()

        if params.get('remove') == 'yes':
            remove_workspaces.delay([self.get_object().id])
            url = reverse_lazy('workspaces:workspace-list', args=[kwargs['workspace']])

        if self.request.headers.get('X-Fetch') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)


class BaseListView(ListView):
    paginate_by = 10

    filter_fields = {}
    select_related = None
    prefetch_related = None

    def _build_filters(self, q):
        params = {}

        for part in (q or '').split():
            if ":" in part:
                field, value = part.split(':')
                try:
                    operator = self.filter_fields[field]
                    params[operator] = value
                except KeyError:
                    continue
            else:
                params['name__icontains'] = part

        return params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.GET.get('q') is not None:
            context['show_all_url'] = self.request.path

        context['title'] = self.model._meta.verbose_name_plural.capitalize()
        context['singular_title'] = self.model._meta.verbose_name.capitalize()
        context['current_workspace'] = self.kwargs['workspace']

        return context

    def get_queryset(self):
        qs = self.model.objects

        q = self.request.GET.get('q')

        params = self._build_filters(q)

        if q is None:
            qs = qs.all()
        else:
            qs = qs.filter(**params)

        if self.select_related is not None:
            qs = qs.select_related(*self.select_related)

        if self.prefetch_related is not None:
            qs = qs.prefetch_related(*self.prefetch_related)

        return qs


@method_decorator(login_required, name='dispatch')
class WorkspaceList(BaseListView):
    model = Workspace

    filter_fields = dict(
        owner='owner__username'
    )

    select_related = None
    prefetch_related = None

    def get_queryset(self):
        return (super().get_queryset().filter(owner=self.request.user) | super().get_queryset().filter(members=self.request.user)).distinct()

    def post(self, *args, **kwargs):
        params = ujson.loads(self.request.body)

        workspace_ids = [t.split('workspace-')[1] for t in params.keys() if 'workspace-' in t]

        if len(workspace_ids) > 0:
            if params.get('remove') == 'yes':
                remove_workspaces.delay(workspace_ids)

            if params.get('duplicate') == 'yes':
                duplicate_workspaces.delay(workspace_ids)

        url = self.request.get_full_path()

        if self.request.headers.get('X-Fetch') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)


class WorkspaceBaseView(object):
    model = Workspace
    fields = [
        'name', 'description'
    ]

    @property
    def success_url(self):
        workspace = self.kwargs['workspace']
        return get_clean_next_url(self.request, reverse_lazy('workspaces:workspace-list', args=[workspace]))

    def form_valid(self, form):
        response = super().form_valid(form)

        url = self.get_success_url()

        if self.request.headers.get('X-Fetch') == 'true':
            return JsonResponse(dict(url=url))

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        workspace = self.kwargs['workspace']
        workspace_add_url = reverse_lazy('workspaces:workspace-add', args=[workspace])
        context['workspace_add_url'] = workspace_add_url
        context['current_workspace'] = workspace
        return context


@method_decorator(login_required, name='dispatch')
class WorkspaceCreateView(WorkspaceBaseView, CreateView):

    def post(self, *args, **kwargs):
        data = ujson.loads(self.request.body)
        form = self.get_form_class()(data)
        return self.form_valid(form)

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.slug = slugify(form.data.get('name', ''))
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class WorkspaceUpdateView(WorkspaceBaseView, UpdateView):

    def post(self, *args, **kwargs):
        data = ujson.loads(self.request.body)

        if data.get('save-as-new'):
            form = self.get_form_class()(data)
        else:
            form = self.get_form_class()(data, instance=self.get_object())

        return self.form_valid(form)


@login_required
def redirect_to_workspace(request):
    first_workspace = request.user.workspace_set.order_by('id').first()
    return HttpResponseRedirect(
        reverse_lazy(
            'stories:story-list', kwargs={'workspace': first_workspace.slug}
        )
    )
