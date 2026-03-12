# Generated manually — Data migration: move milestone data from legacy table to treebeard tree

from django.db import connection, migrations


def migrate_milestones_forward(apps, schema_editor):
    """
    Read from issues_milestone_legacy and insert into the treebeard tree via add_root().
    Then move Epics that had a milestone FK under their new Milestone parent.
    """
    # We must use the real model (not historical) because treebeard's add_root() and move()
    # rely on class methods that historical models don't have.
    from apps.issues.models import BaseIssue, Milestone
    from apps.projects.models import Project

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, project_id, key, title, description, status, due_date,
                   owner_id, created_by_id, priority
            FROM issues_milestone_legacy
            ORDER BY project_id, id
            """
        )
        legacy_milestones = cursor.fetchall()

    if not legacy_milestones:
        return

    # Create a new Milestone (BaseIssue root node) for each legacy milestone.
    # Map old milestone id → new Milestone instance for the epic-move step below.
    milestone_map = {}

    for legacy_id, project_id, _old_key, title, description, status, due_date, owner_id, created_by_id, priority in legacy_milestones:
        project = Project.objects.get(pk=project_id)

        milestone = Milestone(
            project=project,
            title=title,
            description=description or "",
            status=status,
            due_date=due_date,
            assignee_id=owner_id,  # Milestone.owner → BaseIssue.assignee
            created_by_id=created_by_id,
            priority=priority,
        )
        # Generate a new key in the shared {PROJECT_KEY}-N format
        milestone.key = milestone._generate_unique_key()
        BaseIssue.add_root(instance=milestone)
        milestone_map[legacy_id] = milestone

    # Move Epics that had milestone_id set to be children of their new Milestone parent.
    # The issues_epic table still has the milestone_id column at this point.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT baseissue_ptr_id, milestone_id
            FROM issues_epic
            WHERE milestone_id IS NOT NULL
            """
        )
        epic_milestones = cursor.fetchall()

    for epic_id, legacy_milestone_id in epic_milestones:
        if legacy_milestone_id not in milestone_map:
            continue

        milestone = milestone_map[legacy_milestone_id]
        # Refresh to get the latest path after any previous moves
        milestone.refresh_from_db()

        epic = BaseIssue.objects.get(pk=epic_id)
        epic.move(milestone, pos="last-child")

    # Safety check: verify tree integrity after all moves
    BaseIssue.fix_tree()


def migrate_milestones_reverse(apps, schema_editor):
    raise migrations.exceptions.IrreversibleError(
        "Cannot reverse milestone data migration. Restore from backup if needed."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0006_rename_milestone_to_legacy_and_create_new"),
    ]

    operations = [
        migrations.RunPython(
            migrate_milestones_forward,
            migrate_milestones_reverse,
        ),
    ]
