from django.http import Http404
from django.views import View
from django.views.generic.detail import SingleObjectMixin

from apps.projects.models import Project
from apps.projects.registry import project_actions
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from .mixins import ProjectSingleObjectMixin, ProjectViewMixin


class ProjectActionMixin(ProjectViewMixin, LoginAndWorkspaceRequiredMixin, ProjectSingleObjectMixin, SingleObjectMixin):
    """Shared lookup for action + project, with availability check."""

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace)

    def get_action_and_project(self, action_name):
        action = project_actions.get(action_name)
        if action is None:
            raise Http404

        project = self.get_object()

        if not action.is_available(project, self.request.user):
            raise Http404

        return action, project


class ProjectActionConfirmView(ProjectActionMixin, View):
    """GET — returns confirmation modal HTML for an action."""

    def get(self, request, action_name, **kwargs):
        action, project = self.get_action_and_project(action_name)
        return action.get_confirm_response(project, request)


class ProjectActionView(ProjectActionMixin, View):
    """POST — executes a registered project action."""

    def post(self, request, action_name, **kwargs):
        action, project = self.get_action_and_project(action_name)
        return action.execute(project, request)
