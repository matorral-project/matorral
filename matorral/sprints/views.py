from itertools import groupby

import ujson

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView
from rest_framework import viewsets

from matorral.stories.forms import StoryFilterForm
from matorral.stories.tasks import story_set_assignee, story_set_state

from ..utils import get_clean_next_url
from .forms import SprintGroupByForm
from .models import Sprint
from .serializers import SprintSerializer
from .tasks import duplicate_sprints, remove_sprints, reset_sprint


@method_decorator(login_required, name='dispatch')
class SprintDetailView(DetailView):

    model = Sprint

    def get_children(self):
        queryset = self.get_object().story_set\
            .select_related('requester', 'assignee', 'epic', 'state')\
            .order_by('epic__priority', 'priority')

        config = dict(
            epic=('epic__name', lambda story: story.epic and story.epic.title or 'No Epic'),
            state=('state__slug', lambda story: story.state.name),
            requester=('requester__username', lambda story: story.requester and story.requester.username or 'Unset'),
            assignee=('assignee__username', lambda story: story.assignee and story.assignee.username or 'Unassigned'),
        )

        group_by = self.request.GET.get('group_by')

        try:
            order_by, fx = config[group_by]
        except KeyError:
            return [(None, queryset)]
        else:
            queryset = queryset.order_by(order_by)
            foo = [(t[0], list(t[1])) for t in groupby(queryset, key=fx)]
            return foo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['group_by_form'] = SprintGroupByForm(self.request.GET)
        context['objects_by_group'] = self.get_children()
        context['group_by'] = self.request.GET.get('group_by')
        context['filters_form'] = StoryFilterForm(self.request.POST)
        context['current_workspace'] = self.kwargs['workspace']
        return context

    def post(self, *args, **kwargs):
        params = ujson.loads(self.request.body)
        url = self.request.get_full_path()

        if params.get('remove') == 'yes':
            remove_sprints.delay([self.get_object().id])
            url = reverse_lazy('sprints:sprint-list', args=[self.kwargs['workspace']])

        elif params.get('sprint-reset') == 'yes':
            story_ids = [t[6:] for t in params.keys() if 'story-' in t]
            reset_sprint.delay(story_ids)

        else:
            state = params.get('state')
            if isinstance(state, list):
                state = state[0]
            if state:
                story_ids = [t[6:] for t in params.keys() if 'story-' in t]
                story_set_state.delay(story_ids, state)

            assignee = params.get('assignee')
            if isinstance(assignee, list):
                assignee = assignee[0]
            if assignee:
                story_ids = [t[6:] for t in params.keys() if 'story-' in t]
                story_set_assignee.delay(story_ids, assignee)

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)


@method_decorator(login_required, name='dispatch')
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
        context['current_workspace'] = self.kwargs['workspace']

        return context

    def get_queryset(self):
        qs = self.model.objects

        q = self.request.GET.get('q')

        params = dict(workspace__slug=self.kwargs['workspace'])

        if q is None:
            qs = qs.filter(**params)
        else:
            params.update(self._build_filters(q))
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
        params = ujson.loads(self.request.body)

        sprint_ids = [t[7:] for t in params.keys() if 'sprint-' in t]

        if len(sprint_ids) > 0:
            if params.get('remove') == 'yes':
                remove_sprints.delay(sprint_ids)

            if params.get('duplicate') == 'yes':
                duplicate_sprints.delay(sprint_ids)

        url = self.request.get_full_path()

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))
        else:
            return HttpResponseRedirect(url)


class SprintBaseView(object):
    model = Sprint
    fields = [
        'title', 'description', 'starts_at', 'ends_at'
    ]

    @property
    def success_url(self):
        return get_clean_next_url(self.request, reverse_lazy('sprints:sprint-list', args=[self.kwargs['workspace']]))

    def form_valid(self, form):
        response = super().form_valid(form)

        url = self.get_success_url()

        if self.request.META.get('HTTP_X_FETCH') == 'true':
            return JsonResponse(dict(url=url))

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint_add_url = reverse_lazy('sprints:sprint-add', args=[self.kwargs['workspace']])
        context['sprint_add_url'] = sprint_add_url
        context['current_workspace'] = self.kwargs['workspace']
        return context


@method_decorator(login_required, name='dispatch')
class SprintCreateView(SprintBaseView, CreateView):

    def post(self, *args, **kwargs):
        data = ujson.loads(self.request.body)
        form = self.get_form_class()(data)
        return self.form_valid(form)

    def form_valid(self, form):
        form.instance.workspace = self.request.workspace
        return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class SprintUpdateView(SprintBaseView, UpdateView):

    def post(self, *args, **kwargs):
        data = ujson.loads(self.request.body)

        if data.get('save-as-new'):
            form = self.get_form_class()(data)
        else:
            form = self.get_form_class()(data, instance=self.get_object())

        return self.form_valid(form)
