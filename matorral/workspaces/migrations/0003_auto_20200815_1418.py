# Generated by Django 2.2.10 on 2020-08-15 14:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("workspaces", "0002_auto_20200815_1216"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="workspace",
            options={
                "get_latest_by": "created_at",
                "ordering": ["name"],
                "verbose_name": "workspace",
                "verbose_name_plural": "workspaces",
            },
        ),
    ]
