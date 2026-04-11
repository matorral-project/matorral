from dataclasses import dataclass
from enum import Enum

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.issues.helpers import build_htmx_delete_response
from apps.issues.models import BaseIssue
from apps.sprints.forms import SprintBulkOwnerForm
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.models import AuditLog


class ActionType(Enum):
    PRIMARY = "primary"
    MENU = "menu"


class BaseAction:
    """Shared fields for single-sprint and bulk-sprint actions."""

    name = ""
    label = ""
    icon = ""
    confirm = False
    confirm_title = ""
    confirm_body = ""
    css_class = "btn-primary"


class SprintAction(BaseAction):
    """Action that operates on a single sprint (detail page)."""

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


class SprintBulkAction(BaseAction):
    """Action that operates on multiple sprints (list page bulk toolbar).

    To register a new bulk action:
    1. Create a subclass of SprintBulkAction
    2. Set name, label, icon, and other fields
    3. Implement execute() to perform the bulk operation
    4. Optionally override validate() and get_form_class()
    5. Register with @sprint_bulk_actions.register or sprint_bulk_actions.register_instance()
    """

    render_type = "button"  # "button", "dropdown", or "modal"

    def validate(self, queryset, request):
        """Raise ValidationError to abort with user-facing message."""

    def execute(self, queryset, request) -> str:
        """Perform the bulk operation. Return success message string."""
        raise NotImplementedError

    def get_form_class(self):
        """Override to provide extra form fields. Return None for no extra form."""
        return None

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


class SprintActionRegistry:
    def __init__(self):
        self._actions: dict[str, SprintAction] = {}

    def register(self, action_class):
        """Register an action class. Can be used as @decorator."""
        instance = action_class()
        self._actions[instance.name] = instance
        return action_class

    def get(self, name: str) -> SprintAction | None:
        return self._actions.get(name)

    def available_for(self, sprint, user) -> list[SprintAction]:
        return [a for a in self._actions.values() if a.is_available(sprint, user)]

    def primary_for(self, sprint, user) -> list[SprintAction]:
        return [a for a in self.available_for(sprint, user) if a.action_type == ActionType.PRIMARY]

    def menu_for(self, sprint, user) -> list[SprintAction]:
        return [a for a in self.available_for(sprint, user) if a.action_type == ActionType.MENU]


sprint_actions = SprintActionRegistry()


class SprintBulkActionRegistry:
    """Registry for bulk sprint actions.

    Bulk actions are always shown in the toolbar (no is_available filtering).
    Register actions with @registry.register (class decorator) or registry.register_instance().
    """

    def __init__(self):
        self._actions: dict[str, SprintBulkAction] = {}

    def register(self, action_class):
        """Register an action class. Can be used as @decorator."""
        instance = action_class()
        self._actions[instance.name] = instance
        return action_class

    def register_instance(self, instance):
        """Register a pre-built action instance (for parameterized actions)."""
        self._actions[instance.name] = instance

    def get(self, name: str) -> SprintBulkAction | None:
        return self._actions.get(name)

    def all(self) -> list[SprintBulkAction]:
        return list(self._actions.values())


sprint_bulk_actions = SprintBulkActionRegistry()


@dataclass
class BoundAction:
    name: str
    label: str
    icon: str
    css_class: str
    confirm: bool
    url: str
    confirm_url: str
    confirm_title: str = ""
    confirm_body: str = ""
    render_type: str = "button"


def build_sprint_action_context(sprint, user) -> dict:
    """Build primary_actions and menu_actions context for templates."""

    def make_bound(action):
        return BoundAction(
            name=action.name,
            label=str(action.label),
            icon=action.icon,
            css_class=action.css_class,
            confirm=action.confirm,
            url=action.get_url(sprint),
            confirm_url=action.get_confirm_url(sprint),
            confirm_title=str(action.confirm_title),
            confirm_body=str(action.confirm_body),
        )

    return {
        "primary_actions": [make_bound(a) for a in sprint_actions.primary_for(sprint, user)],
        "menu_actions": [make_bound(a) for a in sprint_actions.menu_for(sprint, user)],
    }


def build_sprint_bulk_action_context(workspace) -> dict:
    """Build bulk_actions context for sprint list template."""

    def make_bound(action):
        return BoundAction(
            name=action.name,
            label=str(action.label),
            icon=action.icon,
            css_class=action.css_class,
            confirm=action.confirm,
            url=action.get_url(workspace),
            confirm_url=action.get_confirm_url(workspace),
            confirm_title=str(action.confirm_title),
            confirm_body=str(action.confirm_body),
            render_type=action.render_type,
        )

    return {
        "bulk_actions": [make_bound(a) for a in sprint_bulk_actions.all()],
    }


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
    render_type = "menu"

    def execute(self, queryset, request):
        deleted_count, _deleted_objects = queryset.delete()
        remaining_count = Sprint.objects.for_workspace(request.workspace).count()
        return deleted_count, remaining_count


class BulkStatusAction(SprintBulkAction):
    """Parameterized bulk action for setting sprint status."""

    render_type = "dropdown"

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

    def execute(self, queryset, request):
        selected_pks = list(queryset.values_list("pk", flat=True))

        if self.status == SprintStatus.ACTIVE:
            sprint = Sprint.objects.for_workspace(request.workspace).with_committed_points().get(pk=selected_pks[0])

            try:
                sprint.start()
                return _("Sprint '%(name)s' is now active.") % {"name": sprint.name}
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

        return _("%(count)d sprint(s) updated to %(status)s.") % {"count": updated_count, "status": new_display}


for _value, _label in SprintStatus.choices:
    sprint_bulk_actions.register_instance(BulkStatusAction(_value, _label))


@sprint_bulk_actions.register
class BulkOwnerAction(SprintBulkAction):
    name = "owner"
    label = _("Set Owner")
    icon = "user"
    css_class = "btn-outline"
    render_type = "modal"

    def get_form_class(self):
        return SprintBulkOwnerForm

    def execute(self, queryset, request):
        extra_form = SprintBulkOwnerForm(
            data=request.POST,
            workspace=request.workspace,
            workspace_members=request.workspace_members,
        )
        extra_form.is_valid()
        owner = extra_form.cleaned_data["owner"]

        selected_pks = list(queryset.values_list("pk", flat=True))
        objects = list(Sprint.objects.filter(pk__in=selected_pks).select_related("owner"))
        old_values = {obj.pk: obj.owner.get_display_name() if obj.owner else None for obj in objects}
        new_display = owner.get_display_name() if owner else None

        updated_count = queryset.update(owner=owner)
        AuditLog.objects.bulk_create_for(
            objects, field_name="owner", old_values=old_values, new_display=new_display, actor=request.user
        )

        if owner:
            return _("%(count)d sprint(s) assigned to %(owner)s.") % {"count": updated_count, "owner": new_display}
        return _("%(count)d sprint(s) unassigned.") % {"count": updated_count}
