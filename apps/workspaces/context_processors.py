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
