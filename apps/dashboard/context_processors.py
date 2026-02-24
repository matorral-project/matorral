from apps.dashboard.helpers import get_onboarding_status


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
