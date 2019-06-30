from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from rest_framework import viewsets

from ..utils import get_clean_next_url
from .forms import EpicFilterForm, StoryFilterForm
from .models import Epic, Story, Task
from .serializers import EpicSerializer, StorySerializer, TaskSerializer
from .tasks import (duplicate_stories, remove_stories, story_set_assignee,
                    story_set_state, duplicate_epics, remove_epics,
                    epic_set_owner, epic_set_state, reset_epic)
from alameda.sprints.views import BaseListView, BaseView


class EpicDetailView(DetailView):

    model = Epic

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_list'] = self.get_object().story_set.select_related('requester', 'assignee', 'sprint', 'state')
        return context

    def post(self, *args, **kwargs):
        params = self.request.POST.dict()

        if params.get('remove') == 'yes':
            remove_epics.delay([self.get_object().id])
            return HttpResponseRedirect(reverse_lazy('stories:epic-list'))

        if params.get('epic-reset') == 'yes':
            story_ids = [t[6:] for t in params.keys() if 'story-' in t]
            reset_epic.delay(story_ids)

        return HttpResponseRedirect(self.request.get_full_path())


class EpicViewSet(viewsets.ModelViewSet):
    serializer_class = EpicSerializer
    queryset = Epic.objects.select_related('state', 'state', 'owner')


class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    queryset = Story.objects.select_related('epic', 'sprint', 'state', 'state', 'requester', 'assignee')


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()


class StoryBaseView(BaseView):
    model = Story
    fields = [
        'title', 'description',
        'epic', 'sprint',
        'requester', 'assignee',
        'priority', 'points',
        'state', 'tags',
    ]

    @property
    def success_url(self):
        return get_clean_next_url(self.request, reverse_lazy('stories:story-list'))


@method_decorator(login_required, name='dispatch')
class StoryCreateView(StoryBaseView, CreateView):

    def _get_success_message(self):
        return 'Story successfully created!'

    def get_initial(self):
        initial_dict = dict(requester=self.request.user.id, state='pl')

        epic_id = self.request.GET.get('epic')
        if epic_id is not None:
            initial_dict['epic'] = epic_id

        sprint_id = self.request.GET.get('sprint')
        if sprint_id is not None:
            initial_dict['sprint'] = sprint_id

        return initial_dict


@method_decorator(login_required, name='dispatch')
class StoryUpdateView(StoryBaseView, UpdateView):

    def _get_success_message(self):
        return 'Story successfully updated!'


class EpicBaseView(BaseView):
    model = Epic
    fields = [
        'title', 'description',
        'owner', 'priority',
        'state', 'tags',
    ]

    @property
    def success_url(self):
        return get_clean_next_url(self.request, reverse_lazy('stories:epic-list'))


@method_decorator(login_required, name='dispatch')
class EpicCreateView(EpicBaseView, CreateView):

    def _get_success_message(self):
        return 'Epic successfully created!'

    def get_initial(self):
        return dict(owner=self.request.user.id, state='pl')


@method_decorator(login_required, name='dispatch')
class EpicUpdateView(EpicBaseView, UpdateView):

    def _get_success_message(self):
        return 'Epic successfully updated!'


@method_decorator(login_required, name='dispatch')
class EpicList(BaseListView):
    model = Epic

    filter_fields = dict(
        owner='owner__username',
        state='state__name__iexact',
        label='tags__name__iexact'
    )

    select_related = ['owner', 'state']
    prefetch_related = ['tags']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters_form'] = EpicFilterForm(self.request.POST)
        return context

    def post(self, *args, **kwargs):
        params = self.request.POST.dict()

        epic_ids = [t[5:] for t in params.keys() if 'epic-' in t]

        if len(epic_ids) > 0:
            if params.get('remove') == 'yes':
                remove_epics.delay(epic_ids)

            if params.get('duplicate') == 'yes':
                duplicate_epics.delay(epic_ids)

            if params.get('state') != '--':
                epic_set_state.delay(epic_ids, params['state'])

            if params.get('owner') != '--':
                epic_set_owner.delay(epic_ids, params['owner'])

        return HttpResponseRedirect(self.request.get_full_path())


@method_decorator(login_required, name='dispatch')
class StoryList(BaseListView):
    model = Story

    filter_fields = dict(
        requester='requester__username',
        assignee='assignee__username',
        state='state__name__iexact',
        label='tags__name__iexact',
        sprint='sprint__title__iexact'
    )

    select_related = ['requester', 'assignee', 'state', 'sprint']
    prefetch_related = ['tags']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filters_form'] = StoryFilterForm(self.request.POST)
        return context

    def post(self, *args, **kwargs):
        params = self.request.POST.dict()

        story_ids = [t[6:] for t in params.keys() if 'story-' in t]

        if len(story_ids) > 0:
            if params.get('remove') == 'yes':
                remove_stories.delay(story_ids)

            if params.get('duplicate') == 'yes':
                duplicate_stories.delay(story_ids)

            if params.get('state'):
                story_set_state.delay(story_ids, params['state'])

            if params.get('assignee'):
                story_set_assignee.delay(story_ids, params['assignee'])

        return HttpResponseRedirect(self.request.get_full_path())
