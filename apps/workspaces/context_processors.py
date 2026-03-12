from apps.workspaces.models import Workspace

from .helpers import get_onboarding_session_key, get_onboarding_status


def onboarding_context(request):
    """Add onboarding pending count to all templates for sidebar badge.

    Uses the session to avoid re-running DB queries on every request. The cache is
    invalidated whenever the user completes an onboarding step (project created,
    invitation sent, sprint created, demo explored, or onboarding dismissed).
    """
    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request, "workspace")
        and request.workspace
    ):
        try:
            if request.user.onboarding_completed:
                return {"onboarding_pending_count": 0}
            session_key = get_onboarding_session_key(request.workspace)
            count = request.session.get(session_key)
            if count is None:
                count = get_onboarding_status(request.user, request.workspace)["pending_count"]
                request.session[session_key] = count
            return {"onboarding_pending_count": count}
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
        ws = Workspace.objects.for_user(request.user).first()
        if ws:
            return {"default_workspace": ws}

    return {}
