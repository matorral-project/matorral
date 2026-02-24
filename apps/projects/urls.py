from django.urls import path

from . import views

app_name = "projects"

# Project-scoped URL patterns - mounted at /w/<workspace_slug>/p/
project_urlpatterns = (
    [
        path("", views.ProjectListView.as_view(), name="project_list"),
        path("new/", views.ProjectCreateView.as_view(), name="project_create"),
        path(
            "bulk-delete/",
            views.ProjectBulkDeleteView.as_view(),
            name="projects_bulk_delete",
        ),
        path(
            "bulk-status/",
            views.ProjectBulkStatusView.as_view(),
            name="projects_bulk_status",
        ),
        path("bulk-lead/", views.ProjectBulkLeadView.as_view(), name="projects_bulk_lead"),
        path("<str:key>/", views.ProjectDetailView.as_view(), name="project_detail"),
        path(
            "<str:key>/epics/",
            views.ProjectEpicsEmbedView.as_view(),
            name="project_epics_embed",
        ),
        path(
            "<str:key>/orphan-issues/",
            views.ProjectOrphanIssuesEmbedView.as_view(),
            name="project_orphan_issues_embed",
        ),
        path(
            "<str:key>/epics/new/",
            views.ProjectEpicCreateView.as_view(),
            name="project_epic_create",
        ),
        path(
            "<str:key>/issues/new/<str:issue_type>/",
            views.ProjectIssueCreateView.as_view(),
            name="project_issue_create_typed",
        ),
        path(
            "<str:key>/epics/<str:epic_key>/children/",
            views.ProjectEpicChildrenView.as_view(),
            name="project_epic_children",
        ),
        path(
            "<str:key>/new-milestone/",
            views.ProjectMilestoneCreateView.as_view(),
            name="project_milestone_create",
        ),
        path(
            "<str:key>/inline-edit/",
            views.ProjectRowInlineEditView.as_view(),
            name="project_inline_edit",
        ),
        path(
            "<str:key>/detail-inline-edit/",
            views.ProjectDetailInlineEditView.as_view(),
            name="project_detail_inline_edit",
        ),
        path("<str:key>/edit/", views.ProjectUpdateView.as_view(), name="project_update"),
        path("<str:key>/clone/", views.ProjectCloneView.as_view(), name="project_clone"),
        path(
            "<str:key>/delete/",
            views.ProjectDeleteView.as_view(),
            name="project_delete",
        ),
        path(
            "<str:key>/history/",
            views.ProjectHistoryView.as_view(),
            name="project_history",
        ),
    ],
    "projects",
)
