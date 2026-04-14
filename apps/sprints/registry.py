from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
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
from apps.issues.helpers import build_htmx_delete_response
from apps.issues.models import BaseIssue
from apps.sprints.forms import SprintBulkOwnerForm
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.models import AuditLog

__all__ = [
    "SprintAction",
    "SprintActionRegistry",
    "SprintBulkAction",
    "SprintBulkActionRegistry",
    "build_sprint_action_context",
    "build_sprint_bulk_action_context",
    "sprint_actions",
    "sprint_bulk_actions",
]


class SprintAction(Action):
    """Action that operates on a single sprint (detail page).

    To register a new sprint action:
    1. Create a subclass of SprintAction
    2. Set name, label, icon, and other fields
    3. Set action_type to ActionType.PRIMARY or ActionType.MENU
    4. Implement is_available() to control visibility
    5. Implement execute() to perform the action
    6. Optionally override get_confirm_response() for custom confirmation UI
    7. Register with @sprint_actions.register
    """

    action_type = ActionType.PRIMARY

    def is_available(self, sprint, user) -> bool:
        raise NotImplementedError

    def execute(self, sprint, request):
        raise NotImplementedError

    def get_url(self, sprint) -> str:
        return reverse(
            "sprints:sprint_action",
            kwargs={
                "workspace_slug": sprint.workspace.slug,
                "key": sprint.key,
                "action_name": self.name,
            },
        )

    def get_confirm_url(self, sprint) -> str:
        return reverse(
            "sprints:sprint_action_confirm",
            kwargs={
                "workspace_slug": sprint.workspace.slug,
                "key": sprint.key,
                "action_name": self.name,
            },
        )

    def get_confirm_response(self, sprint, request):
        return render(
            request,
            "sprints/includes/action_confirm_modal.html",
            {
                "action": self,
                "sprint": sprint,
                "post_url": self.get_url(sprint),
            },
        )


class SprintBulkAction(BulkAction):
    """Action that operates on multiple sprints (list page bulk toolbar).

    To register a new bulk action:
    1. Create a subclass of SprintBulkAction
    2. Set name, label, icon, and other fields
    3. Implement execute() to perform the bulk operation
    4. Optionally override validate() and get_form_class()
    5. Register with @sprint_bulk_actions.register or sprint_bulk_actions.register_instance()
    """

    def get_url(self, workspace) -> str:
        return reverse(
            "sprints:sprint_bulk_action",
            kwargs={"workspace_slug": workspace.slug, "action_name": self.name},
        )

    def get_confirm_url(self, workspace) -> str:
        return reverse(
            "sprints:sprint_bulk_action_confirm",
            kwargs={"workspace_slug": workspace.slug, "action_name": self.name},
        )


class SprintActionRegistry(ActionRegistry[SprintAction]):
    pass


sprint_actions = SprintActionRegistry()


class SprintBulkActionRegistry(ActionRegistry[SprintBulkAction]):
    """Registry for bulk sprint actions.

    Bulk actions are always shown in the toolbar (no is_available filtering).
    Register actions with @registry.register (class decorator) or registry.register_instance().
    """


sprint_bulk_actions = SprintBulkActionRegistry()


def build_sprint_action_context(sprint, user) -> dict:
    """Build primary_actions and menu_actions context for templates."""
    return {
        "primary_actions": [BoundAction.from_action(a, sprint) for a in sprint_actions.primary_for(sprint, user)],
        "menu_actions": [BoundAction.from_action(a, sprint) for a in sprint_actions.menu_for(sprint, user)],
    }


def build_sprint_bulk_action_context(workspace) -> dict:
    """Build bulk_actions context for sprint list template."""
    return build_bulk_action_context(sprint_bulk_actions, workspace)


# ============================================================================
# Action registrations
# ============================================================================


@sprint_actions.register
class StartSprintAction(SprintAction):
    name = "start"
    label = _("Start Sprint")
    icon = "play"
    action_type = ActionType.PRIMARY
    confirm = True
    confirm_title = _("Start Sprint?")
    confirm_body = _("This will begin the sprint. Make sure all issues are assigned.")
    css_class = "btn-success"

    def is_available(self, sprint, user):
        return sprint.status == SprintStatus.PLANNING

    def execute(self, sprint, request):
        sprint = Sprint.objects.for_workspace(request.workspace).with_committed_points().get(pk=sprint.pk)

        try:
            sprint.start()
            messages.success(request, _("Sprint started successfully."))
        except ValueError as exc:
            messages.error(request, str(exc))
        except IntegrityError:
            messages.error(request, _("Another sprint is already active in this workspace."))

        return redirect(sprint.get_absolute_url())


@sprint_actions.register
class CompleteSprintAction(SprintAction):
    name = "complete"
    label = _("Complete Sprint")
    icon = "check-circle"
    action_type = ActionType.PRIMARY
    confirm = True
    confirm_title = _("Complete Sprint?")
    confirm_body = _("Incomplete issues will be moved to the next planning sprint.")
    css_class = "btn-success"

    def is_available(self, sprint, user):
        return sprint.status == SprintStatus.ACTIVE

    def execute(self, sprint, request):
        sprint = Sprint.objects.for_workspace(request.workspace).with_completed_points().get(pk=sprint.pk)

        try:
            moved_count, next_sprint = sprint.complete()
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(sprint.get_absolute_url())

        if moved_count > 0:
            messages.success(
                request,
                _("Sprint completed. %(count)d incomplete issue(s) moved to %(sprint)s.")
                % {"count": moved_count, "sprint": next_sprint.name},
            )
        else:
            messages.success(request, _("Sprint completed successfully."))

        return redirect(sprint.get_absolute_url())


@sprint_actions.register
class ArchiveSprintAction(SprintAction):
    name = "archive"
    label = _("Archive")
    icon = "archive"
    action_type = ActionType.MENU
    confirm = True
    confirm_title = _("Archive Sprint?")
    confirm_body = _("Are you sure you want to archive this sprint?")

    def is_available(self, sprint, user):
        return sprint.status not in (SprintStatus.ACTIVE, SprintStatus.ARCHIVED)

    def execute(self, sprint, request):
        try:
            sprint.archive()
            messages.success(request, _("Sprint archived successfully."))
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect(sprint.get_absolute_url())


@sprint_actions.register
class DeleteSprintAction(SprintAction):
    name = "delete"
    label = _("Delete")
    icon = "trash"
    action_type = ActionType.MENU
    confirm = True
    confirm_title = _("Delete Sprint?")
    confirm_body = _("This action cannot be undone.")

    def is_available(self, sprint, user):
        return True

    def get_confirm_response(self, sprint, request):
        item_count = BaseIssue.objects.for_sprint(sprint).count()
        return render(
            request,
            "sprints/includes/action_confirm_modal.html",
            {
                "action": self,
                "sprint": sprint,
                "item_count": item_count,
                "post_url": self.get_url(sprint),
            },
        )

    def execute(self, sprint, request):
        deleted_url = sprint.get_absolute_url()
        redirect_url = reverse("sprints:sprint_list", kwargs={"workspace_slug": request.workspace.slug})

        sprint.delete()
        messages.success(request, _("Sprint deleted successfully."))

        if request.htmx:
            return build_htmx_delete_response(request, deleted_url, redirect_url)

        return redirect(redirect_url)


# ============================================================================
# Bulk action registrations
# ============================================================================


@sprint_bulk_actions.register
class BulkDeleteAction(SprintBulkAction):
    name = "delete"
    label = _("Delete")
    icon = "trash"
    confirm = True
    confirm_title = _("Delete Sprints")
    confirm_body = _("Are you sure you want to delete the selected sprints? This action cannot be undone.")
    css_class = "btn-error"
    render_type = RenderType.MENU
    modal_var = "showBulkDeleteModal"

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        deleted_count, _deleted_objects = queryset.delete()
        remaining_count = Sprint.objects.for_workspace(request.workspace).count()

        message = _("%(count)d sprint(s) deleted successfully.") % {"count": deleted_count}

        return BulkActionResult(message=message, remaining_count=remaining_count)


class BulkStatusAction(SprintBulkAction):
    """Parameterized bulk action for setting sprint status."""

    render_type = RenderType.DROPDOWN

    def __init__(self, status_value, status_label):
        self.name = f"status-{status_value}"
        self.status = status_value
        self.label = status_label
        self.icon = "flag"
        self.css_class = "btn-outline"

    def validate(self, queryset, request):
        if self.status == SprintStatus.ACTIVE and queryset.count() > 1:
            raise ValidationError(
                _("Only one sprint can be active at a time. Please select a single sprint to activate.")
            )

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        selected_pks = list(queryset.values_list("pk", flat=True))

        if self.status == SprintStatus.ACTIVE:
            sprint = Sprint.objects.for_workspace(request.workspace).with_committed_points().get(pk=selected_pks[0])

            try:
                sprint.start()
                message = _("Sprint '%(name)s' is now active.") % {"name": sprint.name}
                return BulkActionResult(message=message)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            except IntegrityError as exc:
                raise ValidationError(_("Another sprint is already active in this workspace.")) from exc

        # For other statuses, use bulk update
        selected_sprints = list(Sprint.objects.filter(pk__in=selected_pks))
        status_choices = dict(SprintStatus.choices)
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in selected_sprints}
        new_display = status_choices.get(self.status, self.status)

        updated_count = queryset.update(status=self.status)
        AuditLog.objects.bulk_create_for(
            selected_sprints,
            field_name="status",
            old_values=old_values,
            new_display=new_display,
            actor=request.user,
        )

        message = _("%(count)d sprint(s) updated to %(status)s.") % {"count": updated_count, "status": new_display}

        return BulkActionResult(message=message)


def _register_status_actions():
    for value, label in SprintStatus.choices:
        sprint_bulk_actions.register_instance(BulkStatusAction(value, label))


_register_status_actions()


@sprint_bulk_actions.register
class BulkOwnerAction(SprintBulkAction):
    name = "owner"
    label = _("Set Owner")
    icon = "user"
    css_class = "btn-outline"
    render_type = RenderType.MODAL
    modal_var = "showBulkOwnerModal"

    def get_form_class(self):
        return SprintBulkOwnerForm

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None):
        owner = (extra_cleaned_data or {}).get("owner")

        selected_pks = list(queryset.values_list("pk", flat=True))
        objects = list(Sprint.objects.filter(pk__in=selected_pks).select_related("owner"))
        old_values = {obj.pk: obj.owner.get_display_name() if obj.owner else None for obj in objects}
        new_display = owner.get_display_name() if owner else None

        updated_count = queryset.update(owner=owner)
        AuditLog.objects.bulk_create_for(
            objects, field_name="owner", old_values=old_values, new_display=new_display, actor=request.user
        )

        if owner:
            message = _("%(count)d sprint(s) assigned to %(owner)s.") % {
                "count": updated_count,
                "owner": new_display,
            }
        else:
            message = _("%(count)d sprint(s) unassigned.") % {"count": updated_count}

        return BulkActionResult(message=message)
