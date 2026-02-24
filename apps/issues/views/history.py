"""
History views for issues and milestones.
"""

from django.shortcuts import get_object_or_404

from apps.issues.models import BaseIssue, Milestone
from apps.issues.views.mixins import IssueViewMixin
from apps.projects.models import Project
from apps.utils.views.history import BaseHistoryView
from apps.workspaces.models import Workspace


class IssueHistoryView(IssueViewMixin, BaseHistoryView):
    """Display history for an issue (Epic, Story, Bug, Chore, or Issue)."""

    def get_template_names(self):
        """Override to use simple template name without #page-content suffix."""
        return [self.template_name]

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(
                BaseIssue.objects.for_project(self.project).select_related("polymorphic_ctype"),
                key=self.kwargs["key"],
            )
        return self._object

    @property
    def model_verbose_name(self):
        obj = self.get_object()
        return obj.get_issue_type_display()


class MilestoneHistoryView(BaseHistoryView):
    """Display history for a milestone."""

    model_verbose_name = "milestone"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["project_key"],
        )

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(
                Milestone.objects.for_project(self.project),
                key=self.kwargs["key"],
            )
        return self._object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        context["project"] = self.project
        context["milestone"] = self.get_object()
        return context
