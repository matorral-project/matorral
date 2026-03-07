# Generated manually — Drop the legacy subtask table after data migration

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("issues", "0004_migrate_subtask_data"),
    ]

    operations = [
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS "issues_subtask_legacy";',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
