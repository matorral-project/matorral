"""
Base history view for displaying audit log entries.
"""

from django.contrib.contenttypes.models import ContentType
from django.views.generic import TemplateView

from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from auditlog.models import LogEntry


class BaseHistoryView(LoginAndWorkspaceRequiredMixin, TemplateView):
    """
    Base view for displaying history/audit log entries.

    Subclasses must implement:
    - get_object(): Return the model instance to show history for
    - model_verbose_name: The human-readable model name (e.g., "story", "epic")
    """

    template_name = "utils/includes/history_list.html"
    model_verbose_name = "item"

    def get_template_names(self):
        """Override to prevent parent mixins from adding #page-content suffix."""
        return [self.template_name]

    def get_object(self):
        """Return the object whose history to display. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement get_object()")

    def get_history_queryset(self):
        """
        Return the queryset of LogEntry objects for this object.
        Queries LogEntry directly using ContentType for reliable results.
        """
        obj = self.get_object()
        content_type = ContentType.objects.get_for_model(obj)
        return (
            LogEntry.objects.filter(
                content_type=content_type,
                object_pk=str(obj.pk),
            )
            .select_related("actor")
            .order_by("-timestamp")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.get_object()
        context["history_entries"] = self.get_history_queryset()
        context["model_verbose_name"] = self.model_verbose_name
        return context
