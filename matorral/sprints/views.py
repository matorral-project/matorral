from itertools import groupby

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework import viewsets

from matorral.generic_ui.views import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView

from .models import Sprint
from .serializers import SprintSerializer


@method_decorator(login_required, name='dispatch')
class SprintViewSet(viewsets.ModelViewSet):
    serializer_class = SprintSerializer
    queryset = Sprint.objects.all()


class SprintDetailView(GenericDetailView):

    model = Sprint

    fields = ('title', 'description', 'state', 'progress', 'starts_at', 'ends_at')

    class ChildrenConfig:
        group_by = None
        select_related = ('requester', 'assignee', 'epic', 'state')
        order_by = ('epic__priority', 'priority')

        table_config = [
            {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
            {'name': 'title', 'title': 'Title', 'widget': 'link'},
            {'name': 'epic', 'title': 'Epic', 'widget': 'link'},
            {'name': 'state', 'title': 'State'},
            {'name': 'priority', 'title': 'Priority'},
            {'name': 'points', 'title': 'Points', 'abbreviation': 'Pts'},
            {'name': 'requester', 'title': 'Requester'},
            {'name': 'assignee', 'title': 'Assignee'},
        ]

    def get_children(self, group_by=None):
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


class SprintList(GenericListView):
    model = Sprint

    default_search = 'title__icontains'

    table_config = [
        {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
        {'name': 'title', 'title': 'Title', 'widget': 'link'},
        {'name': 'state', 'title': 'State'},
        {'name': 'starts_at', 'title': 'Starts'},
        {'name': 'ends_at', 'title': 'Ends'},
        {'name': 'total_points', 'title': 'Points', 'abbreviation': 'Pts'},
        {'name': 'story_count', 'title': 'Stories'},
        {'name': 'progress', 'title': 'progress', 'widget': 'progress'},
        {'name': 'updated_at', 'title': 'Updated'},
    ]

    def get_queryset(self):
        return super().get_queryset().filter(workspace__slug=self.kwargs['workspace'])


class SprintCreateView(GenericCreateView):
    model = Sprint

    fields = [
        'title', 'description', 'starts_at', 'ends_at'
    ]

    def set_attributes(self, request, form):
        form.instance.workspace = self.request.workspace


class SprintUpdateView(GenericUpdateView):
    model = Sprint

    fields = [
        'title', 'description', 'starts_at', 'ends_at'
    ]
