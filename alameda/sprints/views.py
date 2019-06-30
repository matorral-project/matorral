from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView
from rest_framework import viewsets

from ..utils import get_clean_next_url
from .models import Sprint
from .serializers import SprintSerializer
from .tasks import duplicate_sprints, remove_sprints, reset_sprint


class SprintDetailView(DetailView):

    model = Sprint

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_list'] = self.get_object().story_set.select_related('requester', 'assignee', 'epic', 'state')
        return context

    def post(self, *args, **kwargs):
        params = self.request.POST.dict()

        if params.get('remove') == 'yes':
            remove_sprints.delay([self.get_object().id])
            return HttpResponseRedirect(reverse_lazy('sprints:sprint-list'))

        if params.get('sprint-reset') == 'yes':
            story_ids = [t[6:] for t in params.keys() if 'story-' in t]
            reset_sprint.delay(story_ids)

        return HttpResponseRedirect(self.request.get_full_path())


class SprintViewSet(viewsets.ModelViewSet):
    serializer_class = SprintSerializer
    queryset = Sprint.objects.all()


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
                params['title__icontains'] = part

        return params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.GET.get('q') is not None:
            context['show_all_url'] = self.request.path

        context['title'] = self.model._meta.verbose_name_plural.capitalize()
        context['singular_title'] = self.model._meta.verbose_name.capitalize()

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
class SprintList(BaseListView):
    model = Sprint
    filter_fields = {}
    select_related = None
    prefetch_related = None

    def post(self, *args, **kwargs):
        params = self.request.POST.dict()

        sprint_ids = [t[7:] for t in params.keys() if 'sprint-' in t]

        if len(sprint_ids) > 0:
            if params.get('remove') == 'yes':
                remove_sprints.delay(sprint_ids)

            if params.get('duplicate') == 'yes':
                duplicate_sprints.delay(sprint_ids)

        return HttpResponseRedirect(self.request.get_full_path())


class BaseView(object):

    def form_valid(self, form):
        messages.add_message(self.request, messages.INFO, self._get_success_message())
        return super().form_valid(form)


class SprintBaseView(BaseView):
    model = Sprint
    fields = [
        'title', 'description', 'starts_at', 'ends_at'
    ]

    @property
    def success_url(self):
        return get_clean_next_url(self.request, reverse_lazy('sprints:sprint-list'))


@method_decorator(login_required, name='dispatch')
class SprintCreateView(SprintBaseView, CreateView):

    def _get_success_message(self):
        return 'Sprint successfully created!'


@method_decorator(login_required, name='dispatch')
class SprintUpdateView(SprintBaseView, UpdateView):

    def _get_success_message(self):
        return 'Sprint successfully updated!'
