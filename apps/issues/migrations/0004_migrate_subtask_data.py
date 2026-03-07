# Generated manually — Data migration: move subtask data from legacy table to treebeard tree

from collections import defaultdict

from django.db import connection, migrations


# Map old SubtaskStatus values to IssueStatus values
STATUS_MAP = {
    "todo": "draft",
    "in_progress": "in_progress",
    "done": "done",
    "wont_do": "wont_do",
}


def migrate_subtasks_forward(apps, schema_editor):
    """Read from issues_subtask_legacy and insert into the treebeard tree via add_child()."""
    # We must use the real model (not historical) because treebeard's add_child()
    # relies on class methods that historical models don't have.
    from apps.issues.models import BaseIssue, Subtask

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, content_type_id, object_id, title, status, position
            FROM issues_subtask_legacy
            ORDER BY content_type_id, object_id, position, created_at
            """
        )
        rows = cursor.fetchall()

    if not rows:
        return

    # Group subtasks by parent (content_type_id, object_id)
    grouped = defaultdict(list)
    for row in rows:
        _legacy_id, content_type_id, object_id, title, status, position = row
        grouped[(content_type_id, object_id)].append(
            {
                "title": title,
                "status": STATUS_MAP.get(status, "draft"),
                "position": position,
            }
        )

    # For each parent, look up the BaseIssue and add subtask children
    for (_ct_id, object_id), subtask_list in grouped.items():
        try:
            parent = BaseIssue.objects.get(pk=object_id)
        except BaseIssue.DoesNotExist:
            # Parent was deleted; skip orphaned subtasks
            continue

        for subtask_data in subtask_list:
            subtask = Subtask(
                project=parent.project,
                title=subtask_data["title"],
                status=subtask_data["status"],
                priority="medium",
            )
            subtask.key = subtask._generate_unique_key()
            parent.add_child(instance=subtask)


def migrate_subtasks_reverse(apps, schema_editor):
    """Reverse migration: not feasible to reconstruct GenericFK data perfectly. Raise error."""
    raise migrations.exceptions.IrreversibleError(
        "Cannot reverse subtask data migration. Restore from backup if needed."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0003_migrate_subtask_to_baseissue"),
    ]

    operations = [
        migrations.RunPython(
            migrate_subtasks_forward,
            migrate_subtasks_reverse,
        ),
    ]
