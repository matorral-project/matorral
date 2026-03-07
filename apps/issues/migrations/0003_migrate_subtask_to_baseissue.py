# Generated manually — Migrate Subtask from BaseModel to BaseIssue

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0002_initial"),
    ]

    operations = [
        # Step 1: Rename old table so we can read from it during data migration
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='ALTER TABLE "issues_subtask" RENAME TO "issues_subtask_legacy";',
                    reverse_sql='ALTER TABLE "issues_subtask_legacy" RENAME TO "issues_subtask";',
                ),
            ],
            state_operations=[
                # Remove old Subtask model from Django state
                migrations.DeleteModel(
                    name="Subtask",
                ),
            ],
        ),
        # Step 2: Create new Subtask as BaseIssue subclass (both state + DB)
        migrations.CreateModel(
            name="Subtask",
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
                "verbose_name": "Subtask",
                "verbose_name_plural": "Subtasks",
            },
            bases=("issues.baseissue",),
        ),
    ]
