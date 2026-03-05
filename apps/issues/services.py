from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.utils.translation import gettext_lazy as _

from apps.issues.models import BaseIssue, Bug, BugSeverity, Chore, Epic, IssueStatus, Story

from auditlog.models import LogEntry
from django_comments_xtd.models import XtdComment

# Models that can be converted between (work items only, not Epic)
CONVERTIBLE_TYPES = {
    "story": Story,
    "bug": Bug,
    "chore": Chore,
}


class IssueConversionError(Exception):
    """Raised when an issue type conversion fails."""

    pass


def convert_issue_type(
    issue: BaseIssue,
    target_type: str,
    severity: str | None = None,
) -> BaseIssue:
    """
    Convert a work item to a different type, preserving relationships.

    This handles django-polymorphic's multi-table inheritance by:
    1. Creating a new row in the target type's table
    2. Updating the polymorphic_ctype on BaseIssue
    3. Deleting the old type-specific row
    4. Updating ContentType references in generic FKs (comments, history)

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

        # Step 1: Create the new type-specific row
        # We need to insert directly into the target table with the same baseissue_ptr_id
        # Note: priority and estimated_points are on BaseIssue, so they're already preserved
        if target_type == "bug":
            _create_type_row(
                target_model,
                base_issue_id,
                sprint_id=real_issue.sprint_id,
                severity=severity,
            )
        else:
            _create_type_row(target_model, base_issue_id, sprint_id=real_issue.sprint_id)

        # Step 2: Update polymorphic_ctype on BaseIssue
        BaseIssue.objects.filter(pk=base_issue_id).update(polymorphic_ctype=new_content_type)

        # Step 3: Delete the old type-specific row
        _delete_type_row(source_model, base_issue_id)

        # Step 4: Update ContentType references in generic FKs (comments, history)
        _update_generic_fk_content_types(base_issue_id, old_content_type, new_content_type)

        # Step 5: Create audit log entry for the conversion
        _create_conversion_audit_log(base_issue_id, source_type, target_type, new_content_type)

        # Fetch and return the converted instance
        return target_model.objects.get(pk=base_issue_id)


def _create_type_row(
    model_class,
    base_issue_id: int,
    sprint_id: int | None = None,
    severity: str | None = None,
):
    """Insert a row into the type-specific table.

    Note: priority and estimated_points are now on BaseIssue, so we don't
    need to insert them into the child tables.
    """
    table_name = model_class._meta.db_table

    # Build column/value lists based on model
    # Work item tables only have: baseissue_ptr_id, sprint_id (and severity for Bug)
    columns = ["baseissue_ptr_id", "sprint_id"]
    values = [base_issue_id, sprint_id]

    if model_class == Bug:
        columns.append("severity")
        values.append(severity)

    placeholders = ", ".join(["%s"] * len(columns))
    column_names = ", ".join(columns)

    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",  # noqa: S608
            values,
        )


def _delete_type_row(model_class, base_issue_id: int):
    """Delete the row from the type-specific table."""
    table_name = model_class._meta.db_table

    with connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {table_name} WHERE baseissue_ptr_id = %s",  # noqa: S608
            [base_issue_id],
        )


def _update_generic_fk_content_types(issue_id: int, old_ct: ContentType, new_ct: ContentType):
    """Update ContentType references in models with GenericForeignKey to this issue."""
    # Update Comments (django_comments_xtd uses object_pk as string)
    XtdComment.objects.filter(content_type=old_ct, object_pk=str(issue_id)).update(content_type=new_ct)

    # Update Audit Log entries
    LogEntry.objects.filter(content_type=old_ct, object_id=issue_id).update(content_type=new_ct)


def _create_conversion_audit_log(issue_id: int, source_type: str, target_type: str, content_type: ContentType):
    """Create an audit log entry recording the type conversion."""
    # Get the issue for representation
    issue = BaseIssue.objects.get(pk=issue_id)

    LogEntry.objects.create(
        content_type=content_type,
        object_id=issue_id,
        object_pk=str(issue_id),
        object_repr=str(issue),
        action=LogEntry.Action.UPDATE,
        changes={
            "type": [source_type.title(), target_type.title()],
        },
    )


class PromotionError(Exception):
    """Raised when an issue promotion to Epic fails."""

    pass


def promote_to_epic(
    issue: BaseIssue,
    milestone=None,
) -> Epic:
    """
    Promote a work item (Story, Bug, Chore) to an Epic.

    This handles:
    1. Creating a new Epic row with the same baseissue_ptr_id
    2. Updating the polymorphic_ctype to Epic
    3. Deleting the old type-specific row
    4. Moving to root if the issue had a parent (Epics must be root-level)
    5. Subtasks (children of the work item) are preserved as children of the Epic

    Args:
        issue: The BaseIssue instance to promote (must be Story, Bug, or Chore)
        milestone: Optional Milestone to link the Epic to

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
            if isinstance(parent_real, Epic) and hasattr(parent_real, "milestone_id") and parent_real.milestone_id:
                milestone = parent_real.milestone

        # Step 1: Create the Epic row with the same baseissue_ptr_id
        # Note: priority is now on BaseIssue, so it's already preserved
        _create_epic_row(
            base_issue_id,
            milestone_id=milestone.pk if milestone else None,
        )

        # Step 2: Update polymorphic_ctype on BaseIssue
        BaseIssue.objects.filter(pk=base_issue_id).update(polymorphic_ctype=new_content_type)

        # Step 3: Delete the old type-specific row
        _delete_type_row(source_model, base_issue_id)

        # Step 4: Update ContentType references in generic FKs (comments, history)
        _update_generic_fk_content_types_for_epic(base_issue_id, old_content_type, new_content_type)

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

        # Step 7: Convert subtasks (BaseIssue children) to Stories
        # When promoting to Epic, subtasks become Stories as children of the Epic
        _convert_subtasks_to_stories(epic)

        # Step 8: Create audit log entry
        _create_promotion_audit_log(base_issue_id, source_type, new_content_type)

        return epic


def _create_epic_row(
    base_issue_id: int,
    milestone_id: int | None = None,
):
    """Insert a row into the Epic table.

    Note: priority is now on BaseIssue, so we only insert milestone_id here.
    """
    table_name = Epic._meta.db_table

    columns = ["baseissue_ptr_id", "milestone_id"]
    values = [base_issue_id, milestone_id]

    placeholders = ", ".join(["%s"] * len(columns))
    column_names = ", ".join(columns)

    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",  # noqa: S608
            values,
        )


def _update_generic_fk_content_types_for_epic(issue_id: int, old_ct: ContentType, new_ct: ContentType):
    """Update ContentType references for comments and audit log."""
    # Update Comments (django_comments_xtd uses object_pk as string)
    XtdComment.objects.filter(content_type=old_ct, object_pk=str(issue_id)).update(content_type=new_ct)

    # Update Audit Log entries
    LogEntry.objects.filter(content_type=old_ct, object_id=issue_id).update(content_type=new_ct)


def _create_promotion_audit_log(issue_id: int, source_type: str, content_type: ContentType):
    """Create an audit log entry recording the promotion to Epic."""
    # Get the issue for representation
    issue = BaseIssue.objects.get(pk=issue_id)

    LogEntry.objects.create(
        content_type=content_type,
        object_id=issue_id,
        object_pk=str(issue_id),
        object_repr=str(issue),
        action=LogEntry.Action.UPDATE,
        changes={
            "type": [source_type.title(), "Epic"],
        },
    )


def _convert_subtasks_to_stories(epic: Epic) -> None:
    """Convert subtasks (BaseIssue children) to Stories as children of the Epic.

    Each subtask becomes a Story:
    - READY subtasks become DRAFT Stories
    - Other statuses are preserved
    - Priority is inherited from the Epic
    """

    # Get all children (which are BaseIssue instances, formerly subtasks)
    children = list(epic.get_children())

    for child in children:
        # Get the real instance to check polymorphic type
        real_child = child.get_real_instance()

        # Skip if already a Story
        if isinstance(real_child, Story):
            continue

        # Convert subtask to Story
        _convert_single_subtask_to_story(child, epic)


def _convert_single_subtask_to_story(subtask: BaseIssue, epic: Epic) -> None:
    """Convert a single BaseIssue subtask to a Story.

    - READY subtasks become DRAFT Stories
    - Other statuses are preserved
    - Priority is inherited from the Epic
    - Assignee is preserved from the subtask
    """
    # Determine new status (READY -> DRAFT, others preserved)
    new_status = IssueStatus.DRAFT if subtask.status == IssueStatus.READY else subtask.status

    # Inherit priority from epic
    priority = epic.priority

    # Preserve assignee from subtask
    assignee = subtask.assignee

    with transaction.atomic():
        base_issue_id = subtask.pk
        old_content_type = ContentType.objects.get_for_model(BaseIssue)
        new_content_type = ContentType.objects.get_for_model(Story)

        # Step 1: Create the Story row
        _create_story_row(
            base_issue_id,
            sprint_id=None,
        )

        # Step 2: Update BaseIssue (polymorphic_ctype, status, priority, assignee)
        BaseIssue.objects.filter(pk=base_issue_id).update(
            polymorphic_ctype=new_content_type,
            status=new_status,
            priority=priority,
            assignee=assignee,
        )

        # Step 3: Update ContentType references in generic FKs
        _update_generic_fk_content_types_for_epic(base_issue_id, old_content_type, new_content_type)


def _create_story_row(
    base_issue_id: int,
    sprint_id: int | None = None,
):
    """Insert a row into the Story table.

    Note: estimated_points is on BaseIssue, not Story.
    """
    table_name = Story._meta.db_table

    columns = ["baseissue_ptr_id", "sprint_id"]
    values = [base_issue_id, sprint_id]

    placeholders = ", ".join(["%s"] * len(columns))
    column_names = ", ".join(columns)

    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})",  # noqa: S608
            values,
        )
