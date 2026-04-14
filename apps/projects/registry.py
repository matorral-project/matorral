from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.generic_ui.actions import (
    Action,
    ActionRegistry,
    ActionType,
    BoundAction,
    BulkAction,
    BulkActionResult,
    RenderType,
    build_bulk_action_context,
)
from apps.issues.cascade import build_cascade_oob_response_bulk
from apps.projects.forms import BulkLeadForm, BulkMoveForm
from apps.projects.models import Project, ProjectStatus
from apps.projects.tasks import start_move_operation
from apps.utils.models import AuditLog

__all__ = [
    "ProjectAction",
    "ProjectActionRegistry",
    "ProjectBulkAction",
    "ProjectBulkActionRegistry",
    "build_project_action_context",
    "build_project_bulk_action_context",
    "project_actions",
    "project_bulk_actions",
]


class ProjectAction(Action):
    """Action that operates on a single project (detail page)."""

    action_type = ActionType.PRIMARY

    def is_available(self, project, user) -> bool:
        raise NotImplementedError

    def execute(self, project, request):
        raise NotImplementedError

    def get_url(self, project) -> str:
        return reverse(
            "projects:project_action",
            kwargs={
                "workspace_slug": project.workspace.slug,
                "key": project.key,
                "action_name": self.name,
            },
        )

    def get_confirm_url(self, project) -> str:
        return reverse(
            "projects:project_action_confirm",
            kwargs={
                "workspace_slug": project.workspace.slug,
                "key": project.key,
                "action_name": self.name,
            },
        )


class ProjectBulkAction(BulkAction):
    """Action that operates on multiple projects (list page bulk toolbar).

    Project bulk confirm modals are pre-rendered inline in the list template
    (see ``projects/includes/bulk_*_modal.html``) rather than fetched via a
    separate confirm endpoint, so ``get_confirm_url`` is intentionally empty.
    """

    def get_url(self, workspace) -> str:
        return reverse(
            "projects:project_bulk_action",
            kwargs={"workspace_slug": workspace.slug, "action_name": self.name},
        )

    def get_confirm_url(self, workspace) -> str:
        return ""


class ProjectActionRegistry(ActionRegistry[ProjectAction]):
    pass


project_actions = ProjectActionRegistry()


class ProjectBulkActionRegistry(ActionRegistry[ProjectBulkAction]):
    """Registry for bulk project actions."""


project_bulk_actions = ProjectBulkActionRegistry()


def build_project_action_context(project, user) -> dict:
    """Build primary_actions and menu_actions context for templates."""
    return {
        "primary_actions": [BoundAction.from_action(a, project) for a in project_actions.primary_for(project, user)],
        "menu_actions": [BoundAction.from_action(a, project) for a in project_actions.menu_for(project, user)],
    }


def build_project_bulk_action_context(workspace) -> dict:
    """Build bulk_actions context for project list template."""
    return build_bulk_action_context(project_bulk_actions, workspace)


# ============================================================================
# Bulk action registrations
# ============================================================================


@project_bulk_actions.register
class BulkDeleteAction(ProjectBulkAction):
    name = "delete"
    label = _("Delete")
    icon = "trash"
    confirm = True
    confirm_title = _("Delete Projects")
    confirm_body = _("Are you sure you want to delete the selected projects? This action cannot be undone.")
    css_class = "btn-error"
    render_type = RenderType.MENU
    modal_var = "showBulkDeleteModal"

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        deleted_count, _deleted_objects = queryset.delete()
        remaining_count = Project.objects.for_workspace(request.workspace).count()

        message = _("%(count)d project(s) deleted successfully.") % {"count": deleted_count}

        return BulkActionResult(message=message, remaining_count=remaining_count)


class BulkStatusAction(ProjectBulkAction):
    """Parameterized bulk action for setting project status."""

    render_type = RenderType.DROPDOWN
    css_class = "btn-outline"
    icon = "flag"

    def __init__(self, status_value, status_label):
        self.name = f"status-{status_value}"
        self.status = status_value
        self.label = status_label

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        status_choices = dict(ProjectStatus.choices)
        objects = list(queryset)
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in objects}
        new_display = status_choices.get(self.status, self.status)

        updated_count = queryset.update(status=self.status)
        AuditLog.objects.bulk_create_for(
            objects,
            field_name="status",
            old_values=old_values,
            new_display=new_display,
            actor=request.user,
        )

        request._project_cascade_objects = objects
        request._project_cascade_status = self.status

        message = _("%(count)d project(s) updated to %(status)s.") % {"count": updated_count, "status": new_display}

        return BulkActionResult(message=message)


def _register_status_actions():
    for value, label in ProjectStatus.choices:
        project_bulk_actions.register_instance(BulkStatusAction(value, label))


_register_status_actions()


@project_bulk_actions.register
class BulkLeadAction(ProjectBulkAction):
    name = "lead"
    label = _("Set Lead")
    icon = "user"
    css_class = "btn-outline"
    render_type = RenderType.MODAL
    modal_var = "showBulkLeadModal"

    def get_form_class(self):
        return BulkLeadForm

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        lead = (extra_cleaned_data or {}).get("lead")

        objects = list(queryset.select_related("lead"))
        old_values = {obj.pk: obj.lead.get_display_name() if obj.lead else None for obj in objects}
        new_display = lead.get_display_name() if lead else None

        updated_count = queryset.update(lead=lead)
        AuditLog.objects.bulk_create_for(
            objects,
            field_name="lead",
            old_values=old_values,
            new_display=new_display,
            actor=request.user,
        )

        if lead:
            message = _("%(count)d project(s) assigned to %(lead)s.") % {
                "count": updated_count,
                "lead": new_display,
            }
        else:
            message = _("%(count)d project(s) lead removed.") % {"count": updated_count}

        return BulkActionResult(message=message)


@project_bulk_actions.register
class BulkMoveAction(ProjectBulkAction):
    name = "move"
    label = _("Move to Workspace")
    icon = "arrow-right-arrow-left"
    css_class = "btn-outline"
    render_type = RenderType.MODAL
    modal_var = "showBulkMoveModal"

    def get_form_class(self):
        return BulkMoveForm

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        target_workspace = (extra_cleaned_data or {}).get("workspace")
        project_ids = list(queryset.values_list("pk", flat=True))

        operation_id = start_move_operation(project_ids, target_workspace.pk)

        request._move_operation_id = operation_id
        request._move_total = len(project_ids)

        message = _("%(count)d project(s) queued for move.") % {"count": len(project_ids)}

        return BulkActionResult(message=message)

    def emits_cascade(self):  # pragma: no cover - trivial
        return False


def apply_bulk_cascade(request, response):
    """If the last bulk status action stashed cascade objects on the request,
    wrap the response with the cascade OOB payload."""
    cascade_objects = getattr(request, "_project_cascade_objects", None)
    if cascade_objects and request.htmx:
        status = getattr(request, "_project_cascade_status", None)
        return build_cascade_oob_response_bulk(request, cascade_objects, status, response)
    return response
