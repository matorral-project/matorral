from django.core.files.storage import default_storage
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from apps.users.models import User

from allauth.account.internal.flows.manage_email import emit_email_changed
from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed


@receiver(pre_save, sender=User)
def remove_previous_picture(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_picture_file = sender.objects.get(pk=instance.pk).avatar
    except sender.DoesNotExist:
        return

    if (
        old_picture_file
        and old_picture_file.name != instance.avatar.name
        and default_storage.exists(old_picture_file.name)
    ):
        default_storage.delete(old_picture_file.name)


@receiver(post_delete, sender=User)
def delete_picture(sender, instance, **kwargs):
    if instance.avatar and default_storage.exists(instance.avatar.name):
        default_storage.delete(instance.avatar.name)


@receiver(email_confirmed)
def set_user_email_as_primary(sender, request, email_address, **kwargs):
    """
    When email address gets confirmed, make it the primary email and notify the old address.
    """
    try:
        old_primary = EmailAddress.objects.get(user=email_address.user, primary=True)
    except EmailAddress.DoesNotExist:
        return

    email_address.set_as_primary()
    emit_email_changed(request, old_primary, email_address)
