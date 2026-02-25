from django.dispatch import receiver

from allauth.account.signals import user_signed_up

from .helpers import create_default_workspace_for_user, get_open_invitations_for_user
from .invitations import get_invitation_id_from_request, process_invitation
from .models import Invitation


@receiver(user_signed_up)
def add_user_to_workspace(request, user, **kwargs):
    """Adds the user to the workspace if there is an invitation in the URL."""
    invitation_id = get_invitation_id_from_request(request)
    if invitation_id:
        try:
            invitation = Invitation.objects.get(id=invitation_id)
            process_invitation(invitation, user)
        except Invitation.DoesNotExist:
            pass
    elif not user.workspaces.exists() and not get_open_invitations_for_user(user):
        create_default_workspace_for_user(user)
