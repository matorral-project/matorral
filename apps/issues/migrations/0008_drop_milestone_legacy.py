# Generated manually — Drop legacy milestone table and the orphaned milestone_id column from issues_epic

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0007_migrate_milestone_data"),
    ]

    operations = [
        # Drop the milestone_id column from issues_epic (data already migrated to tree)
        migrations.RunSQL(
            sql='ALTER TABLE "issues_epic" DROP COLUMN IF EXISTS "milestone_id";',
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Drop the legacy milestone table
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "issues_milestone_legacy";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
