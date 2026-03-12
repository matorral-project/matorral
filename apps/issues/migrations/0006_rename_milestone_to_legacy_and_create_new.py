# Generated manually — Migrate Milestone from BaseModel to BaseIssue (treebeard + polymorphic)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0005_drop_subtask_legacy_table"),
    ]

    operations = [
        # Step 1: Rename old table so we can read from it during data migration.
        # Also remove the old Milestone model and Epic.milestone FK from Django state
        # (the actual DB column is intentionally left in place for the data migration).
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "issues_milestone" RENAME TO "issues_milestone_legacy";',
                    reverse_sql='ALTER TABLE "issues_milestone_legacy" RENAME TO "issues_milestone";',
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="epic",
                    name="milestone",
                ),
                migrations.DeleteModel(
                    name="Milestone",
                ),
            ],
        ),
        # Step 2: Create new Milestone as BaseIssue subclass (both state + DB)
        migrations.CreateModel(
            name="Milestone",
            fields=[
                (
                    "baseissue_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="issues.baseissue",
                    ),
                ),
            ],
            options={
                "verbose_name": "Milestone",
                "verbose_name_plural": "Milestones",
            },
            bases=("issues.baseissue",),
        ),
    ]
