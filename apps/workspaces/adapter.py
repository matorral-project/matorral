from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.users.adapters import UserEmailAsUsernameAdapter

from allauth.account import app_settings as allauth_app_settings
from allauth.core.internal.httpkit import headed_redirect_response

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

    def respond_email_verification_sent(self, request, user):
        """Keep the bot honeypot's fake response fake.

        The base implementation redirects to the "check your email" page even when
        email verification is switched off, which tells a signer-up that a link is on
        its way when none can ever arrive.
        """
        if (
            user is None
            and allauth_app_settings.EMAIL_VERIFICATION == allauth_app_settings.EmailVerificationMethod.NONE
        ):
            return HttpResponseRedirect(getattr(settings, "LOGIN_REDIRECT_URL", "/"))

        return headed_redirect_response("account_email_verification_sent")

    def get_signup_redirect_url(self, request):
        """Land a brand new user in their own workspace instead of "/".

        Runs after login, so ``request.user`` is the account just created. An explicit
        ``?next=`` still wins: allauth checks it before calling this.
        """
        if request.user.is_authenticated:
            workspace = request.user.workspaces.first()
            if workspace:
                return workspace.get_absolute_url()

        return super().get_signup_redirect_url(request)

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

        return settings.LOGIN_REDIRECT_URL
