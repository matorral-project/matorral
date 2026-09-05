from .actions import ProjectActionConfirmView, ProjectActionView
from .bulk import ProjectBulkActionView
from .crud import (
    MoveProgressView,
    ProjectCreateView,
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
    "MoveProgressView",
    "ProjectActionConfirmView",
    "ProjectActionView",
    "ProjectBulkActionView",
    "ProjectCreateView",
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
