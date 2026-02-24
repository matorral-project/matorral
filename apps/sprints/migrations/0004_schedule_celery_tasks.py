from django.db import migrations


def create_periodic_tasks(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    interval, _ = IntervalSchedule.objects.get_or_create(every=60, period="minutes")
    PeriodicTask.objects.update_or_create(
        name="create-next-sprints",
        defaults={
            "task": "apps.sprints.tasks.create_next_sprints",
            "interval": interval,
            "expire_seconds": 60 * 60,
            "enabled": True,
        },
    )

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="7",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
    )
    PeriodicTask.objects.update_or_create(
        name="reset-demo-workspace-data",
        defaults={
            "task": "apps.workspaces.tasks.reset_demo_workspace_data",
            "crontab": crontab,
            "expire_seconds": 60 * 60,
            "enabled": True,
        },
    )


def delete_periodic_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name__in=["create-next-sprints", "reset-demo-workspace-data"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sprints", "0003_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_periodic_tasks, delete_periodic_tasks),
    ]
