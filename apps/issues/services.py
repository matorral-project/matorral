from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from apps.issues.models import BaseIssue, Bug, BugSeverity, Chore, Epic, Story, Subtask
from apps.utils.models import AuditLog

from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django_comments_xtd.models import XtdComment

# Models that can be converted between (work items only, not Epic or Subtask or Milestone)
CONVERTIBLE_TYPES = {
    "story": Story,
    "bug": Bug,
    "chore": Chore,
}


class IssueConversionError(Exception):
    """Raised when an issue type conversion fails."""

    pass


def convert_issue_type(
    issue: Story | Bug | Chore,
    target_type: str,
    severity: str | None = None,
) -> BaseIssue:
    """
    Convert a work item to a different type, preserving relationships.

    This handles django-polymorphic's multi-table inheritance by:
    1. Creating a new row in the target type's table
    2. Updating the polymorphic_ctype on BaseIssue
    3. Deleting the old type-specific row
    4. Updating ContentType references in generic FKs (comments, history, subtasks)

    Args:
        issue: The BaseIssue instance to convert (must be Story, Bug, or Chore)
        target_type: The target type name ("story", "bug", "chore")
        severity: Bug severity (required when converting to Bug, ignored otherwise)

    Returns:
        The converted issue instance

    Raises:
        IssueConversionError: If the conversion cannot be performed
    """
    # Get the real instance (in case a BaseIssue was passed)
    real_issue = issue.get_real_instance()
    source_type = real_issue.get_issue_type()

    # Validate source type is convertible (not Epic)
    if source_type not in CONVERTIBLE_TYPES:
        raise IssueConversionError(_("%(type)s cannot be converted to another type.") % {"type": source_type.title()})

    # Validate target type
    if target_type not in CONVERTIBLE_TYPES:
        raise IssueConversionError(_("Cannot convert to %(type)s.") % {"type": target_type})

    # No-op if already the target type
    if source_type == target_type:
        return real_issue

    # Validate severity for Bug conversion
    if target_type == "bug":
        if not severity:
            severity = BugSeverity.MINOR
        elif severity not in [s[0] for s in BugSeverity.choices]:
            raise IssueConversionError(_("Invalid severity value."))

    target_model = CONVERTIBLE_TYPES[target_type]
    source_model = CONVERTIBLE_TYPES[source_type]

    # Get ContentTypes for updating generic FKs
    old_content_type = ContentType.objects.get_for_model(source_model)
    new_content_type = ContentType.objects.get_for_model(target_model)

    with transaction.atomic():
        base_issue_id = real_issue.pk

        # Step 1-2: Delete old child row and create new one (suppress auditlog
        # signals since these are internal type-conversion operations, not user edits)
        sprint_id = real_issue.sprint_id
        with disable_auditlog():
            models.Model.delete(real_issue, keep_parents=True)

            # Restore pk cleared by Model.delete(); the BaseIssue row still exists
            real_issue.pk = base_issue_id
            create_kwargs = {"sprint_id": sprint_id}

            if target_type == "bug":
                create_kwargs["severity"] = severity

            target_model.objects.create_from_super(
                BaseIssue.objects.non_polymorphic().get(pk=base_issue_id),
                **create_kwargs,
            )

        # Step 3: Update ContentType references in generic FKs:

        # Update Comments (django_comments_xtd uses object_pk as string)
        XtdComment.objects.filter(content_type=old_content_type, object_pk=str(base_issue_id)).update(
            content_type=new_content_type
        )

        # Update Audit Log entries
        LogEntry.objects.filter(content_type=old_content_type, object_id=base_issue_id).update(
            content_type=new_content_type
        )

        # Fetch the converted instance before creating audit log
        converted = target_model.objects.get(pk=base_issue_id)

        # Step 5: Create audit log entry for the conversion
        AuditLog.objects.create_for(
            converted,
            field_name="type",
            old_value=source_type.title(),
            new_value=target_type.title(),
        )

        return converted


class PromotionError(Exception):
    """Raised when an issue promotion to Epic fails."""

    pass


def promote_to_epic(
    issue: BaseIssue,
    milestone=None,
    convert_subtasks: bool = True,
) -> Epic:
    """
    Promote a work item (Story, Bug, Chore) to an Epic.

    This handles:
    1. Creating a new Epic row with the same baseissue_ptr_id
    2. Updating the polymorphic_ctype to Epic
    3. Deleting the old type-specific row
    4. Moving to root if the issue had a parent (Epics must be root-level)
    5. Converting subtasks to Stories as children of the new Epic (optional)
    6. Updating ContentType references in comments, history

    Args:
        issue: The BaseIssue instance to promote (must be Story, Bug, or Chore)
        milestone: Optional Milestone to link the Epic to
        convert_subtasks: If True, convert subtasks to Stories; if False, delete them

    Returns:
        The promoted Epic instance

    Raises:
        PromotionError: If the promotion cannot be performed
    """
    # Get the real instance (in case a BaseIssue was passed)
    real_issue = issue.get_real_instance()
    source_type = real_issue.get_issue_type()

    # Validate source type is a work item (not Epic)
    if source_type == "epic":
        raise PromotionError(_("Epic cannot be promoted to Epic."))

    if source_type not in CONVERTIBLE_TYPES:
        raise PromotionError(_("%(type)s cannot be promoted to Epic.") % {"type": source_type.title()})

    source_model = CONVERTIBLE_TYPES[source_type]

    # Get ContentTypes
    old_content_type = ContentType.objects.get_for_model(source_model)
    new_content_type = ContentType.objects.get_for_model(Epic)

    with transaction.atomic():
        base_issue_id = real_issue.pk
        parent = real_issue.get_parent()
        had_parent = parent is not None

        # Inherit parent epic's milestone if no milestone explicitly provided
        if had_parent and milestone is None:
            parent_real = parent.get_real_instance()
            if isinstance(parent_real, Epic) and parent_real.milestone_id:
                milestone = parent_real.milestone

        # Collect subtasks before any changes (treebeard tree children)
        subtasks = list(real_issue.get_children().instance_of(Subtask))

        # Step 1-2: Delete old child row and create Epic row (suppress auditlog
        # signals since these are internal type-conversion operations, not user edits)
        with disable_auditlog():
            models.Model.delete(real_issue, keep_parents=True)
            # Restore pk cleared by Model.delete(); the BaseIssue row still exists
            real_issue.pk = base_issue_id
            Epic.objects.create_from_super(
                BaseIssue.objects.non_polymorphic().get(pk=base_issue_id),
                milestone_id=milestone.pk if milestone else None,
            )

        # Step 3: Update ContentType references in generic FKs:

        # Update Comments (django_comments_xtd uses object_pk as string)
        XtdComment.objects.filter(content_type=old_content_type, object_pk=str(base_issue_id)).update(
            content_type=new_content_type
        )

        # Update Audit Log entries
        LogEntry.objects.filter(content_type=old_content_type, object_id=base_issue_id).update(
            content_type=new_content_type
        )

        # Step 5: Get the Epic instance
        epic = Epic.objects.get(pk=base_issue_id)

        # Step 6: Move to root if it had a parent (Epics must be root-level)
        if had_parent:
            # Move to be a sibling of any root node (making it a root itself)
            any_root = BaseIssue.get_first_root_node()
            if any_root:
                epic.move(any_root, pos="last-sibling")
            # If no root exists, it's already at root after parent removal
            # Refresh from DB to get updated path
            epic.refresh_from_db()

        # Step 7: Handle subtasks
        if subtasks:
            if convert_subtasks:
                _convert_subtasks_to_stories(subtasks, epic)
            # Always delete the original subtasks (treebeard-aware delete)
            BaseIssue.objects.filter(pk__in=[s.pk for s in subtasks]).delete()

        # Step 8: Create audit log entry for the promotion
        AuditLog.objects.create_for(
            epic,
            field_name="type",
            old_value=source_type.title(),
            new_value="Epic",
        )

        return epic


def _convert_subtasks_to_stories(subtasks: list[Subtask], epic: Epic):
    """Convert subtasks to Story instances as children of the Epic."""
    for subtask in subtasks:
        # Subtask already uses IssueStatus values directly
        story = Story(
            project=epic.project,
            title=subtask.title,
            status=subtask.status,
            priority=epic.priority,
        )
        story.key = story._generate_unique_key()

        # Add as child of the Epic
        epic.add_child(instance=story)
