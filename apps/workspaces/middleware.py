import contextlib

from django.contrib.auth import get_user_model
from django.utils.functional import SimpleLazyObject

from apps.workspaces.context import set_current_workspace, unset_current_workspace
from apps.workspaces.models import Membership, Workspace


def _get_workspace(request, view_kwargs):
    if not hasattr(request, "_cached_workspace"):
        workspace_slug = view_kwargs.get("workspace_slug")
        workspace = None
        if workspace_slug:
            try:
                workspace = Workspace.objects.get(slug=workspace_slug)
                request.session["workspace"] = workspace.id
            except Workspace.DoesNotExist:
                pass
        if workspace is None and "workspace" in request.session:
            try:
                workspace = Workspace.objects.get(id=request.session["workspace"])
            except Workspace.DoesNotExist:
                del request.session["workspace"]
        request._cached_workspace = workspace
    return request._cached_workspace


def _get_workspace_membership(request):
    if not hasattr(request, "_cached_workspace_membership"):
        membership = None
        if request.user.is_authenticated and request.workspace:
            with contextlib.suppress(Membership.DoesNotExist):
                membership = Membership.objects.get(workspace=request.workspace, user=request.user)
        request._cached_workspace_membership = membership
    return request._cached_workspace_membership


def _get_workspace_members(request):
    """Return workspace members for the current workspace, cached on the request."""
    if not hasattr(request, "_cached_workspace_members"):
        workspace_members = None
        if request.workspace:
            User = get_user_model()
            workspace_members = User.objects.for_workspace(request.workspace).for_choices().order_by("email")
        request._cached_workspace_members = workspace_members
    return request._cached_workspace_members


class WorkspacesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            unset_current_workspace(getattr(request, "__workspace_context_token", None))

    def process_view(self, request, view_func, view_args, view_kwargs):
        request.workspace = SimpleLazyObject(lambda: _get_workspace(request, view_kwargs))
        request.workspace_membership = SimpleLazyObject(lambda: _get_workspace_membership(request))
        request.workspace_members = SimpleLazyObject(lambda: _get_workspace_members(request))
        request.__workspace_context_token = set_current_workspace(request.workspace)
