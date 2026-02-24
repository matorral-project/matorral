"""
History views for projects.
"""

from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from apps.projects.views.mixins import ProjectViewMixin
from apps.utils.views.history import BaseHistoryView


class ProjectHistoryView(ProjectViewMixin, BaseHistoryView):
    """Display history for a project."""

    model_verbose_name = "project"

    def get_template_names(self):
        """Override to use simple template name without #page-content suffix."""
        return [self.template_name]

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(
                Project.objects.for_workspace(self.workspace),
                key=self.kwargs["key"],
            )
        return self._object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.get_object()
        return context
