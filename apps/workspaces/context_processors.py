from .helpers import get_onboarding_status


def onboarding_context(request):
    """Add onboarding pending count to all templates for sidebar badge."""
    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request, "workspace")
        and request.workspace
    ):
        try:
            return {"onboarding_pending_count": get_onboarding_status(request.user, request.workspace)["pending_count"]}
        except Exception:
            pass
    return {"onboarding_pending_count": 0}


def default_workspace(request):
    """Provide the default workspace for the current request in templates."""
    workspace = getattr(request, "workspace", None)
    if workspace:
        return {"default_workspace": workspace}

    # Fallback: try to find user's first workspace
    if hasattr(request, "user") and request.user.is_authenticated:
        from apps.workspaces.models import Workspace

        ws = Workspace.objects.for_user(request.user).first()
        if ws:
            return {"default_workspace": ws}

    return {}
