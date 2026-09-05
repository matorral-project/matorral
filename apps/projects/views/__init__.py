from .actions import ProjectActionConfirmView, ProjectActionView
from .bulk import ProjectBulkActionView
from .crud import (
    MoveProgressView,
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
    ProjectMoveView,
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
    "ProjectMoveView",
    "ProjectOrphanIssuesEmbedView",
    "ProjectRowInlineEditView",
    "ProjectUpdateView",
]
