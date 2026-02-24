"""
Template tags for formatting audit log history entries.
"""

from django import template
from django.utils.translation import gettext_lazy as _

from auditlog.models import LogEntry

register = template.Library()


# Fields that should show "edited X" instead of "set X to Y"
TEXT_FIELDS = {"description", "goal"}

# Human-readable field names
FIELD_LABELS = {
    "name": _("name"),
    "key": _("key"),
    "description": _("description"),
    "status": _("status"),
    "lead": _("lead"),
    "goal": _("goal"),
    "start_date": _("start date"),
    "end_date": _("end date"),
    "owner": _("owner"),
    "capacity": _("capacity"),
    "title": _("title"),
    "due_date": _("due date"),
    "priority": _("priority"),
    "milestone": _("milestone"),
    "assignee": _("assignee"),
    "estimated_points": _("points"),
    "sprint": _("sprint"),
    "severity": _("severity"),
}


def _get_field_label(field_name: str) -> str:
    """Get human-readable label for a field name."""
    return str(FIELD_LABELS.get(field_name, field_name.replace("_", " ")))


def _format_value(value) -> str:
    """Format a value for display."""
    if value is None or value == "":
        return str(_("empty"))
    if isinstance(value, bool):
        return str(_("Yes") if value else _("No"))
    return str(value)


def _format_field_change(field_name: str, old_value, new_value) -> str:
    """Format a single field change."""
    field_label = _get_field_label(field_name)

    if field_name in TEXT_FIELDS:
        return str(_("edited %(field)s") % {"field": field_label})

    new_display = _format_value(new_value)
    return str(_("set %(field)s to %(value)s") % {"field": field_label, "value": new_display})


@register.simple_tag
def format_history_entry(entry: LogEntry, model_verbose_name: str = None) -> str:
    """
    Format a LogEntry into a human-readable summary.

    Args:
        entry: The LogEntry object to format
        model_verbose_name: Optional model name for CREATE actions (e.g., "story", "epic")

    Returns:
        A human-readable string describing the change

    Examples:
        - "created this story"
        - "edited description"
        - "set status to In Progress and priority to High"
    """
    action = entry.action

    # Handle CREATE
    if action == LogEntry.Action.CREATE:
        if model_verbose_name:
            return str(_("created this %(model)s") % {"model": model_verbose_name.lower()})
        return str(_("created this item"))

    # Handle DELETE
    if action == LogEntry.Action.DELETE:
        if model_verbose_name:
            return str(_("deleted this %(model)s") % {"model": model_verbose_name.lower()})
        return str(_("deleted this item"))

    # Handle UPDATE
    if action == LogEntry.Action.UPDATE:
        changes = entry.changes
        if not changes:
            return str(_("made changes"))

        change_descriptions = []
        for field_name, values in changes.items():
            # values is [old_value, new_value]
            if isinstance(values, list) and len(values) == 2:
                old_value, new_value = values
                change_descriptions.append(_format_field_change(field_name, old_value, new_value))

        if not change_descriptions:
            return str(_("made changes"))

        if len(change_descriptions) == 1:
            return change_descriptions[0]

        # Join multiple changes with "and"
        if len(change_descriptions) == 2:
            return str(
                _("%(first)s and %(second)s")
                % {
                    "first": change_descriptions[0],
                    "second": change_descriptions[1],
                }
            )

        # For 3+ changes, use commas and "and"
        last = change_descriptions[-1]
        rest = ", ".join(change_descriptions[:-1])
        return str(_("%(rest)s, and %(last)s") % {"rest": rest, "last": last})

    # Handle ACCESS (if enabled)
    if action == LogEntry.Action.ACCESS:
        if model_verbose_name:
            return str(_("viewed this %(model)s") % {"model": model_verbose_name.lower()})
        return str(_("viewed this item"))

    return str(_("made changes"))


@register.simple_tag
def history_action_icon(entry: LogEntry) -> str:
    """
    Return a Font Awesome icon class for the given action type.
    """
    action = entry.action

    if action == LogEntry.Action.CREATE:
        return "fa-plus-circle text-success"
    if action == LogEntry.Action.UPDATE:
        return "fa-pencil text-info"
    if action == LogEntry.Action.DELETE:
        return "fa-trash text-error"
    if action == LogEntry.Action.ACCESS:
        return "fa-eye text-base-content"

    return "fa-circle text-base-content"


@register.simple_tag
def history_action_label(entry: LogEntry) -> str:
    """
    Return a human-readable label for the action type.
    """
    action = entry.action

    if action == LogEntry.Action.CREATE:
        return str(_("Created"))
    if action == LogEntry.Action.UPDATE:
        return str(_("Updated"))
    if action == LogEntry.Action.DELETE:
        return str(_("Deleted"))
    if action == LogEntry.Action.ACCESS:
        return str(_("Accessed"))

    return str(_("Changed"))
