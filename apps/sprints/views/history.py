"""
History views for sprints.
"""

from django.shortcuts import get_object_or_404

from apps.sprints.models import Sprint
from apps.sprints.views.mixins import SprintViewMixin
from apps.utils.views.history import BaseHistoryView


class SprintHistoryView(SprintViewMixin, BaseHistoryView):
    """Display history for a sprint."""

    model_verbose_name = "sprint"

    def get_template_names(self):
        """Override to use simple template name without #page-content suffix."""
        return [self.template_name]

    def get_object(self):
        if not hasattr(self, "_object"):
            self._object = get_object_or_404(
                Sprint.objects.for_workspace(self.workspace),
                key=self.kwargs["key"],
            )
        return self._object

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sprint"] = self.get_object()
        return context
