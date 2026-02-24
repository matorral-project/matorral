from django.urls import path

from . import views

app_name = "workspaces"

# Workspace-scoped URL patterns (require workspace_slug)
_workspace_patterns = [
    path(
        "<slug:workspace_slug>/",
        views.WorkspaceDetailView.as_view(),
        name="workspace_detail",
    ),
    path(
        "<slug:workspace_slug>/settings/",
        views.manage_workspace,
        name="manage_workspace",
    ),
    path(
        "<slug:workspace_slug>/settings/delete/",
        views.delete_workspace,
        name="delete_workspace",
    ),
    path(
        "<slug:workspace_slug>/settings/members/",
        views.manage_workspace_members,
        name="manage_workspace_members",
    ),
    path(
        "<slug:workspace_slug>/settings/members/<int:membership_id>/",
        views.workspace_membership_details,
        name="workspace_membership_details",
    ),
    path(
        "<slug:workspace_slug>/settings/members/<int:membership_id>/remove/",
        views.remove_workspace_membership,
        name="remove_workspace_membership",
    ),
    path(
        "<slug:workspace_slug>/settings/invite/<slug:invitation_id>/",
        views.resend_invitation,
        name="resend_invitation",
    ),
    path(
        "<slug:workspace_slug>/settings/invite/",
        views.send_invitation_view,
        name="send_invitation",
    ),
    path(
        "<slug:workspace_slug>/settings/invite/cancel/<slug:invitation_id>/",
        views.cancel_invitation_view,
        name="cancel_invitation",
    ),
]

# Global workspace URLs (no workspace_slug, e.g. invitations, workspace list)
_global_patterns = [
    path("", views.manage_workspaces, name="manage_workspaces"),
    path("create/", views.create_workspace, name="create_workspace"),
    path(
        "invitation/<slug:invitation_id>/",
        views.accept_invitation,
        name="accept_invitation",
    ),
    path(
        "invitation/<slug:invitation_id>/signup/",
        views.SignupAfterInvite.as_view(),
        name="signup_after_invite",
    ),
]

# Combined patterns for mounting at /w/ — all under the "workspaces" namespace
# Global patterns must come first so fixed paths like "create/" are matched
# before the catch-all <slug:workspace_slug>/ pattern.
urlpatterns = _global_patterns + _workspace_patterns

# Standalone workspace URLs (mounted at /w/)
standalone_urlpatterns = (urlpatterns, "workspaces")
