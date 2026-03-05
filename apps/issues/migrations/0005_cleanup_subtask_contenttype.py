# Generated Django 6.0.2 on 2026-03-04 15:00

from django.db import migrations


def remove_subtask_contenttype(apps, schema_editor):
    """Remove the Subtask ContentType entry after model deletion."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    ContentType.objects.filter(app_label="issues", model="subtask").delete()


class Migration(migrations.Migration):
    """Clean up the Subtask ContentType entry after model deletion."""

    dependencies = [
        ("issues", "0004_delete_subtask"),
    ]

    operations = [
        migrations.RunPython(
            remove_subtask_contenttype,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
