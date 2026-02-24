from django.conf import settings
from django.urls import reverse

from apps.users.adapters import UserEmailAsUsernameAdapter

from .invitations import clear_invite_from_session
from .models import Invitation


class AcceptInvitationAdapter(UserEmailAsUsernameAdapter):
    """
    Adapter that checks for an invitation id in the session and redirects
    to accepting it after login.

    Necessary to use workspace invitations with social login.

    Also restricts signups to invitation-only when ACCOUNT_ALLOW_SIGNUPS is False.
    """

    def is_open_for_signup(self, request):
        if getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", False):
            return True

        invitation_id = request.session.get("invitation_id")
        if not invitation_id:
            return False
        return Invitation.objects.filter(id=invitation_id, is_accepted=False).exists()

    def get_login_redirect_url(self, request):
        if request.session.get("invitation_id"):
            invite_id = request.session.get("invitation_id")
            try:
                invite = Invitation.objects.get(id=invite_id)
                if not invite.is_accepted:
                    return reverse(
                        "workspaces:accept_invitation",
                        args=[request.session["invitation_id"]],
                    )
                else:
                    clear_invite_from_session(request)
            except Invitation.DoesNotExist:
                pass

        if request.user.is_authenticated:
            workspace = request.user.workspaces.first()
            if workspace:
                return workspace.get_absolute_url()

        return getattr(settings, "LOGIN_REDIRECT_URL", "/")
