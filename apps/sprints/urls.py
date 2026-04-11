from django.urls import path

from apps.sprints import views

app_name = "sprints"

# Workspace-scoped URL patterns - mounted at /w/<workspace_slug>/sprints/
workspace_urlpatterns = [
    path("", views.SprintListView.as_view(), name="sprint_list"),
    path("new/", views.SprintCreateView.as_view(), name="sprint_create"),
    # Bulk actions
    path(
        "bulk-action/<str:action_name>/confirm/",
        views.SprintBulkActionConfirmView.as_view(),
        name="sprint_bulk_action_confirm",
    ),
    path("bulk-action/<str:action_name>/", views.SprintBulkActionView.as_view(), name="sprint_bulk_action"),
    # Single sprint views
    path("<str:key>/", views.SprintDetailView.as_view(), name="sprint_detail"),
    path(
        "<str:key>/inline-edit/",
        views.SprintRowInlineEditView.as_view(),
        name="sprint_inline_edit",
    ),
    path(
        "<str:key>/detail-inline-edit/",
        views.SprintDetailInlineEditView.as_view(),
        name="sprint_detail_inline_edit",
    ),
    path("<str:key>/edit/", views.SprintUpdateView.as_view(), name="sprint_update"),
    # Action dispatch
    path(
        "<str:key>/action/<str:action_name>/confirm/",
        views.SprintActionConfirmView.as_view(),
        name="sprint_action_confirm",
    ),
    path(
        "<str:key>/action/<str:action_name>/",
        views.SprintActionView.as_view(),
        name="sprint_action",
    ),
    # Embedded issue list and add issues modal
    path(
        "<str:key>/issues/",
        views.SprintIssueListEmbedView.as_view(),
        name="sprint_issues_embed",
    ),
    path(
        "<str:key>/add-issues/",
        views.SprintAddIssuesView.as_view(),
        name="sprint_add_issues",
    ),
    path(
        "<str:key>/remove-issue/<str:issue_key>/",
        views.SprintRemoveIssueView.as_view(),
        name="sprint_remove_issue",
    ),
    path("<str:key>/history/", views.SprintHistoryView.as_view(), name="sprint_history"),
    # Add issue to sprint (from issue row menu)
    path(
        "add-to-sprint/<str:issue_key>/",
        views.IssueAddToSprintView.as_view(),
        name="issue_add_to_sprint",
    ),
    path(
        "add-to-sprint/<str:issue_key>/confirm/",
        views.IssueAddToSprintConfirmView.as_view(),
        name="issue_add_to_sprint_confirm",
    ),
]
