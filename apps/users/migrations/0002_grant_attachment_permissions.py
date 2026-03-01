from django.db import migrations


def grant_permissions(apps, schema_editor):
    User = apps.get_model("users", "User")
    Permission = apps.get_model("auth", "Permission")
    try:
        add_perm = Permission.objects.get(codename="add_attachment")
        delete_perm = Permission.objects.get(codename="delete_attachment")
    except Permission.DoesNotExist:
        return
    for user in User.objects.all():
        user.user_permissions.add(add_perm, delete_perm)


def revoke_permissions(apps, schema_editor):
    User = apps.get_model("users", "User")
    Permission = apps.get_model("auth", "Permission")
    try:
        add_perm = Permission.objects.get(codename="add_attachment")
        delete_perm = Permission.objects.get(codename="delete_attachment")
    except Permission.DoesNotExist:
        return
    for user in User.objects.all():
        user.user_permissions.remove(add_perm, delete_perm)


class Migration(migrations.Migration):
    dependencies = [
        ("attachments", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(grant_permissions, revoke_permissions),
    ]
