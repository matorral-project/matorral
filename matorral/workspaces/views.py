from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from rest_framework import viewsets

from matorral.generic_ui.views import GenericCreateView, GenericDetailView, GenericListView, GenericUpdateView

from .models import Workspace
from .serializers import WorkspaceSerializer


@method_decorator(login_required, name='dispatch')
class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer
    queryset = Workspace.objects.all()


@method_decorator(login_required, name='dispatch')
class WorkspaceDetailView(GenericDetailView):

    model = Workspace

    fields = ('name', 'description', 'owner', 'updated_at')

    class ChildrenConfig:
        group_by = None
    
        select_related = None

        table_config = [
            {'name': 'id', 'title': 'Identification Number', 'abbreviation': 'ID'},
            {'name': 'username', 'title': 'Userame'},
            {'name': 'first_name', 'title': 'First Name'},
            {'name': 'last_name', 'title': 'Last Name'},
            {'name': 'email', 'title': 'Email'},
        ]

    def get_children(self, group_by=None):
        return self.get_object().members.order_by('username')


@method_decorator(login_required, name='dispatch')
class WorkspaceList(GenericListView):
    model = Workspace

    paginate_by = 10

    filter_fields = dict(
        owner='owner__username'
    )

    default_search = 'name__icontains'

    select_related = ['owner']

    view_config = [
        {'name': 'name', 'title': 'Name', 'widget': 'link'},
        {'name': 'description', 'title': 'Description'},
        {'name': 'owner', 'title': 'Owner'},
        {'name': 'updated_at', 'title': 'Updated'},
    ]

    def get_queryset(self):
        return (super().get_queryset().filter(owner=self.request.user) | super().get_queryset().filter(members=self.request.user)).distinct()


@method_decorator(login_required, name='dispatch')
class WorkspaceCreateView(GenericCreateView):
    model = Workspace

    fields = [
        'name', 'description'
    ]

    def set_attributes(self, request, form):
        form.instance.owner = self.request.user
        form.instance.slug = slugify(form.data.get('name', ''))


@method_decorator(login_required, name='dispatch')
class WorkspaceUpdateView(GenericUpdateView):
    model = Workspace

    fields = [
        'name', 'description'
    ]
