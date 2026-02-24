from django.utils.decorators import method_decorator

from apps.workspaces.decorators import login_and_workspace_membership_required, workspace_admin_required


class WorkspaceObjectViewMixin:
    """
    Abstract mixin for Django class-based views for a model that belongs to a Workspace.
    """

    def get_queryset(self):
        """Narrow queryset to only include objects of this workspace."""
        return self.model.for_workspace.all()


class LoginAndWorkspaceRequiredMixin(WorkspaceObjectViewMixin):
    """
    Verify that the current user is authenticated and a member of the workspace.
    """

    @method_decorator(login_and_workspace_membership_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class WorkspaceAdminRequiredMixin(WorkspaceObjectViewMixin):
    """
    Verify that the current user is authenticated and admin of the workspace.
    """

    @method_decorator(workspace_admin_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
