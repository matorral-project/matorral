from itertools import groupby

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, UpdateView

from matorral.generic_ui.views import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView
from matorral.sprints.models import Sprint

from rest_framework import viewsets

from .models import Epic, Story, Task
from .serializers import EpicSerializer, StorySerializer, TaskSerializer


@method_decorator(login_required, name='dispatch')
class EpicViewSet(viewsets.ModelViewSet):
    serializer_class = EpicSerializer
    queryset = Epic.objects.select_related('state', 'state', 'owner')


@method_decorator(login_required, name='dispatch')
class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    queryset = Story.objects.select_related('epic', 'sprint', 'state', 'state', 'requester', 'assignee')


@method_decorator(login_required, name='dispatch')
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()


@method_decorator(login_required, name='dispatch')
class EpicDetailView(GenericDetailView):
    model = Epic
    fields = ('title', 'owner', 'state', 'priority', 'progress', 'updated_at')

    class ChildrenConfig:
        group_by = None
        select_related = ('requester', 'assignee', 'epic', 'state')
        order_by = ('epic__priority', 'priority')

        table_config = [
            {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
            {'name': 'title', 'title': 'Title', 'widget': 'link'},
            {'name': 'state', 'title': 'State'},
            {'name': 'priority', 'title': 'Priority'},
            {'name': 'points', 'title': 'Points', 'abbreviation': 'Pts'},
            {'name': 'requester', 'title': 'Requester'},
            {'name': 'assignee', 'title': 'Assignee'},
        ]

    def get_children(self, group_by=None):
        queryset = self.get_object().story_set.select_related('requester', 'assignee', 'sprint', 'state')

        config = dict(
            sprint=('sprint__starts_at', lambda story: story.sprint and story.sprint.title or 'No sprint'),
            state=('state__slug', lambda story: story.state.name),
            requester=('requester__id', lambda story: story.requester and story.requester.username or 'Unset'),
            assignee=('assignee__id', lambda story: story.assignee and story.assignee.username or 'Unassigned'),
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


@method_decorator(login_required, name='dispatch')
class StoryDetailView(GenericDetailView):
    model = Story
    fields = ('title', 'epic', 'assignee', 'state', 'priority', 'updated_at')


@method_decorator(login_required, name='dispatch')
class EpicList(GenericListView):
    model = Epic
    
    filter_fields = dict(
        owner='owner__username',
        state='state__name__iexact',
        label='tags__name__iexact'
    )

    select_related = ['owner', 'state']
    prefetch_related = ['tags']

    default_search = 'title__icontains'

    view_config = [
        {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
        {'name': 'title', 'title': 'Title', 'widget': 'link'},
        {'name': 'state', 'title': 'State'},
        {'name': 'priority', 'title': 'Priority'},
        {'name': 'total_points', 'title': 'Points', 'abbreviation': 'Pts'},
        {'name': 'story_count', 'title': 'Stories'},
        {'name': 'progress', 'title': 'progress', 'widget': 'progress'},
        {'name': 'owner', 'title': 'Owner'},
    ]

    def get_queryset(self):
        return super().get_queryset().filter(workspace__slug=self.kwargs['workspace'])


@method_decorator(login_required, name='dispatch')
class StoryList(GenericListView):
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

    default_search = 'title__icontains'

    view_config = [
        {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
        {'name': 'title', 'title': 'Title', 'widget': 'link'},
        {'name': 'epic', 'title': 'Epic', 'widget': 'link'},
        {'name': 'state', 'title': 'State'},
        {'name': 'priority', 'title': 'Priority'},
        {'name': 'points', 'title': 'Points', 'abbreviation': 'Pts'},
        {'name': 'requester', 'title': 'Requester'},
        {'name': 'assignee', 'title': 'Assignee'},
    ]

    def get_queryset(self):
        return super().get_queryset().filter(workspace__slug=self.kwargs['workspace'])


@method_decorator(login_required, name='dispatch')
class StoryCreateView(GenericCreateView):
    model = Story

    fields = [
        'title', 'description',
        'epic', 'sprint',
        'assignee',
        'priority', 'points',
        'state', 'tags',
    ]

    def set_attributes(self, request, form):
        form.instance.requester = self.request.user
        form.instance.workspace = self.request.workspace


@method_decorator(login_required, name='dispatch')
class StoryUpdateView(GenericUpdateView):
    model = Story

    fields = [
        'title', 'description',
        'epic', 'sprint',
        'requester', 'assignee',
        'priority', 'points',
        'state', 'tags',
    ]


@method_decorator(login_required, name='dispatch')
class EpicCreateView(GenericCreateView):
    model = Epic

    fields = [
        'title', 'description',
        'owner', 'priority',
        'state', 'tags',
    ]

    def set_attributes(self, request, form):
        form.instance.workspace = self.request.workspace


@method_decorator(login_required, name='dispatch')
class EpicUpdateView(GenericUpdateView):
    model = Epic

    fields = [
        'title', 'description',
        'owner', 'priority',
        'state', 'tags',
    ]
