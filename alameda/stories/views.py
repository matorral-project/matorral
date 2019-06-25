from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from rest_framework import viewsets

from .models import Epic, Story, Task
from .serializers import EpicSerializer, StorySerializer, TaskSerializer
from alameda.sprints.views import BaseListView, BaseView


class EpicDetailView(DetailView):

    model = Epic

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object_list'] = self.get_object().story_set.all()
        return context


class EpicViewSet(viewsets.ModelViewSet):
    serializer_class = EpicSerializer
    queryset = Epic.objects.select_related('state', 'state', 'owner')


class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    queryset = Story.objects.select_related('epic', 'sprint', 'state', 'state', 'owner', 'assignee')


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()


class StoryBaseView(BaseView):
    model = Story
    fields = [
        'title', 'description',
        'epic', 'sprint',
        'owner', 'assignee',
        'priority', 'points',
        'state', 'tags',
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['cancel_url'] = reverse_lazy('stories:story-list')

        epic_id = self.request.GET.get('epic')
        if epic_id is not None:
            context['cancel_url'] = reverse_lazy('stories:epic-detail', args=[epic_id])

        sprint_id = self.request.GET.get('sprint')
        if sprint_id is not None:
            context['cancel_url'] = reverse_lazy('sprints:sprint-detail', args=[sprint_id])

        return context


@method_decorator(login_required, name='dispatch')
class StoryCreateView(StoryBaseView, CreateView):

    def _get_success_message(self):
        return 'Story successfully created!'

    def get_initial(self):
        initial_dict = dict(owner=self.request.user.id, state='pl')

        epic_id = self.request.GET.get('epic')
        if epic_id is not None:
            initial_dict['epic'] = epic_id

        sprint_id = self.request.GET.get('sprint')
        if sprint_id is not None:
            initial_dict['sprint'] = sprint_id

        return initial_dict

    @property
    def success_url(self):
        epic_id = self.request.GET.get('epic')
        if epic_id is not None:
            return reverse_lazy('stories:epic-detail', args=[epic_id])

        sprint_id = self.request.GET.get('sprint')

        if sprint_id is not None:
            return reverse_lazy('sprints:sprint-detail', args=[sprint_id])

        epic_id = self.request.GET.get('epic')
        if epic_id is not None:
            return reverse_lazy('stories:epic-detail', args=[epic_id])

        return reverse_lazy('stories:story-list')


@method_decorator(login_required, name='dispatch')
class StoryUpdateView(StoryBaseView, UpdateView):

    success_url = reverse_lazy('stories:story-list')

    def _get_success_message(self):
        return 'Story successfully updated!'


class EpicBaseView(BaseView):
    model = Epic
    fields = [
        'title', 'description',
        'owner', 'priority',
        'state', 'tags',
    ]
    success_url = reverse_lazy('stories:epic-list')


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


@method_decorator(login_required, name='dispatch')
class StoryList(BaseListView):
    model = Story

    filter_fields = dict(
        owner='owner__username',
        assignee='assignee__username',
        state='state__name__iexact',
        label='tags__name__iexact',
        sprint='sprint__title__iexact'
    )

    select_related = ['owner', 'assignee', 'state', 'sprint']
    prefetch_related = ['tags']
