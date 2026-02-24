from django.urls import path

from apps.sprints import views

app_name = "sprints"

# Workspace-scoped URL patterns - mounted at /w/<workspace_slug>/sprints/
workspace_urlpatterns = [
    path("", views.SprintListView.as_view(), name="sprint_list"),
    path("new/", views.SprintCreateView.as_view(), name="sprint_create"),
    # Bulk actions
    path("bulk-delete/", views.SprintBulkDeleteView.as_view(), name="sprints_bulk_delete"),
    path("bulk-status/", views.SprintBulkStatusView.as_view(), name="sprints_bulk_status"),
    path("bulk-owner/", views.SprintBulkOwnerView.as_view(), name="sprints_bulk_owner"),
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
    path("<str:key>/delete/", views.SprintDeleteView.as_view(), name="sprint_delete"),
    path("<str:key>/start/", views.SprintStartView.as_view(), name="sprint_start"),
    path(
        "<str:key>/complete/",
        views.SprintCompleteView.as_view(),
        name="sprint_complete",
    ),
    path("<str:key>/archive/", views.SprintArchiveView.as_view(), name="sprint_archive"),
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
