from .bulk import ProjectBulkDeleteView, ProjectBulkLeadView, ProjectBulkStatusView
from .crud import (
    ProjectCloneView,
    ProjectCreateView,
    ProjectDeleteView,
    ProjectDetailInlineEditView,
    ProjectDetailView,
    ProjectEpicChildrenView,
    ProjectEpicCreateView,
    ProjectEpicsEmbedView,
    ProjectIssueCreateView,
    ProjectListView,
    ProjectMilestoneCreateView,
    ProjectOrphanIssuesEmbedView,
    ProjectRowInlineEditView,
    ProjectUpdateView,
)
from .history import ProjectHistoryView

__all__ = [
    "ProjectBulkDeleteView",
    "ProjectBulkLeadView",
    "ProjectBulkStatusView",
    "ProjectCloneView",
    "ProjectCreateView",
    "ProjectDeleteView",
    "ProjectDetailInlineEditView",
    "ProjectDetailView",
    "ProjectEpicChildrenView",
    "ProjectEpicCreateView",
    "ProjectEpicsEmbedView",
    "ProjectHistoryView",
    "ProjectIssueCreateView",
    "ProjectListView",
    "ProjectMilestoneCreateView",
    "ProjectOrphanIssuesEmbedView",
    "ProjectRowInlineEditView",
    "ProjectUpdateView",
]
