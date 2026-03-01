from django.urls import path

from . import views

app_name = "issues"

# Workspace-scoped URL patterns - mounted at /w/<workspace_slug>/issues/
# Note: This is a list, not a tuple with namespace - it will use the "issues" namespace when included
workspace_urlpatterns = [
    path(
        "cascade-status/",
        views.CascadeStatusApplyView.as_view(),
        name="cascade_status_apply",
    ),
    path("", views.WorkspaceIssueListView.as_view(), name="workspace_issue_list"),
    path(
        "new/<str:issue_type>/",
        views.WorkspaceIssueCreateView.as_view(),
        name="workspace_issue_create_typed",
    ),
    path(
        "bulk-delete/",
        views.WorkspaceIssueBulkDeleteView.as_view(),
        name="workspace_issues_bulk_delete",
    ),
    path(
        "bulk-delete-preview/",
        views.WorkspaceIssueBulkDeletePreviewView.as_view(),
        name="workspace_issues_bulk_delete_preview",
    ),
    path(
        "bulk-status/",
        views.WorkspaceIssueBulkStatusView.as_view(),
        name="workspace_issues_bulk_status",
    ),
    path(
        "bulk-priority/",
        views.WorkspaceIssueBulkPriorityView.as_view(),
        name="workspace_issues_bulk_priority",
    ),
    path(
        "bulk-remove-from-sprint/",
        views.WorkspaceIssueBulkRemoveFromSprintView.as_view(),
        name="workspace_issues_bulk_remove_from_sprint",
    ),
    path(
        "bulk-add-to-sprint/",
        views.WorkspaceIssueBulkAddToSprintView.as_view(),
        name="workspace_issues_bulk_add_to_sprint",
    ),
    path(
        "bulk-assignee/",
        views.WorkspaceIssueBulkAssigneeView.as_view(),
        name="workspace_issues_bulk_assignee",
    ),
    path(
        "bulk-milestone/",
        views.WorkspaceIssueBulkMilestoneView.as_view(),
        name="workspace_issues_bulk_milestone",
    ),
]

# Project-scoped URL patterns - mounted at /w/<workspace_slug>/p/<project_key>/issues/
project_urlpatterns = (
    [
        path("new/", views.IssueCreateView.as_view(), name="issue_create"),
        path(
            "new/<str:issue_type>/",
            views.IssueCreateView.as_view(),
            name="issue_create_typed",
        ),
        path("<str:key>/", views.IssueDetailView.as_view(), name="issue_detail"),
        path(
            "<str:key>/issues-embed/",
            views.EpicIssueListEmbedView.as_view(),
            name="epic_issues_embed",
        ),
        path(
            "<str:key>/new-issue/<str:issue_type>/",
            views.EpicIssueCreateView.as_view(),
            name="epic_new_issue",
        ),
        path("<str:key>/edit/", views.IssueUpdateView.as_view(), name="issue_update"),
        path("<str:key>/clone/", views.IssueCloneView.as_view(), name="issue_clone"),
        path(
            "<str:key>/convert/",
            views.IssueConvertTypeView.as_view(),
            name="issue_convert",
        ),
        path(
            "<str:key>/promote/",
            views.IssuePromoteToEpicView.as_view(),
            name="issue_promote",
        ),
        path("<str:key>/delete/", views.IssueDeleteView.as_view(), name="issue_delete"),
        path(
            "<str:key>/children/",
            views.IssueChildrenView.as_view(),
            name="issue_children",
        ),
        path("<str:key>/move/", views.IssueMoveView.as_view(), name="issue_move"),
        path(
            "<str:key>/inline-edit/",
            views.IssueRowInlineEditView.as_view(),
            name="issue_inline_edit",
        ),
        path(
            "<str:key>/detail-inline-edit/",
            views.EpicDetailInlineEditView.as_view(),
            name="epic_detail_inline_edit",
        ),
        path(
            "<str:key>/issue-detail-inline-edit/",
            views.IssueDetailInlineEditView.as_view(),
            name="issue_detail_inline_edit",
        ),
        path(
            "<str:key>/comments/",
            views.IssueCommentsView.as_view(),
            name="issue_comments",
        ),
        path(
            "<str:key>/comments/post/",
            views.IssueCommentPostView.as_view(),
            name="issue_comment_post",
        ),
        path(
            "<str:key>/comments/<int:comment_pk>/edit/",
            views.IssueCommentEditView.as_view(),
            name="issue_comment_edit",
        ),
        path(
            "<str:key>/comments/<int:comment_pk>/delete/",
            views.IssueCommentDeleteView.as_view(),
            name="issue_comment_delete",
        ),
        path("<str:key>/history/", views.IssueHistoryView.as_view(), name="issue_history"),
        # Subtask URLs
        path(
            "<str:key>/subtasks/",
            views.SubtaskListView.as_view(),
            name="issue_subtasks",
        ),
        path(
            "<str:key>/subtasks/add/",
            views.SubtaskCreateView.as_view(),
            name="issue_subtask_add",
        ),
        path(
            "<str:key>/subtasks/<int:subtask_pk>/edit/",
            views.SubtaskInlineEditView.as_view(),
            name="issue_subtask_edit",
        ),
        path(
            "<str:key>/subtasks/<int:subtask_pk>/delete/",
            views.SubtaskDeleteView.as_view(),
            name="issue_subtask_delete",
        ),
        path(
            "<str:key>/subtasks/<int:subtask_pk>/toggle/",
            views.SubtaskStatusToggleView.as_view(),
            name="issue_subtask_toggle",
        ),
    ],
    "issues",
)

# Project-level milestone URL patterns - will be mounted at
# /w/<workspace_slug>/p/<project_key>/milestones/
# These patterns require a project_key - they operate on milestones within a specific project
milestones_urlpatterns = [
    path("new/", views.MilestoneCreateView.as_view(), name="milestone_create"),
    # Single milestone views
    path("<str:key>/", views.MilestoneDetailView.as_view(), name="milestone_detail"),
    path(
        "<str:key>/issues/",
        views.MilestoneIssueListEmbedView.as_view(),
        name="milestone_issues_embed",
    ),
    path("<str:key>/edit/", views.MilestoneUpdateView.as_view(), name="milestone_update"),
    path(
        "<str:key>/delete/",
        views.MilestoneDeleteView.as_view(),
        name="milestone_delete",
    ),
    path("<str:key>/clone/", views.MilestoneCloneView.as_view(), name="milestone_clone"),
    path(
        "<str:key>/new-epic/",
        views.MilestoneEpicCreateView.as_view(),
        name="milestone_new_epic",
    ),
    path(
        "<str:key>/new-issue/<str:issue_type>/",
        views.MilestoneIssueCreateView.as_view(),
        name="milestone_new_issue",
    ),
    path(
        "<str:key>/inline-edit/",
        views.MilestoneRowInlineEditView.as_view(),
        name="milestone_inline_edit",
    ),
    path(
        "<str:key>/detail-inline-edit/",
        views.MilestoneDetailInlineEditView.as_view(),
        name="milestone_detail_inline_edit",
    ),
    path(
        "<str:key>/history/",
        views.MilestoneHistoryView.as_view(),
        name="milestone_history",
    ),
]
