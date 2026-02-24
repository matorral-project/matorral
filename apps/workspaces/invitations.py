from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from apps.users.models import CustomUser

from .limits import check_member_limit
from .models import Invitation


def send_invitation(invitation):
    project_name = Site.objects.get_current().name
    email_context = {
        "invitation": invitation,
        "project_name": project_name,
    }
    send_mail(
        subject=_("You're invited to {}!").format(project_name),
        message=render_to_string("workspaces/email/invitation.txt", context=email_context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        fail_silently=False,
        html_message=render_to_string("workspaces/email/invitation.html", context=email_context),
    )


def process_invitation(invitation: Invitation, user: CustomUser):
    check_member_limit(invitation.workspace)
    invitation.workspace.members.add(user, through_defaults={"role": invitation.role})
    invitation.is_accepted = True
    invitation.accepted_by = user
    invitation.save()


def get_invitation_id_from_request(request):
    return request.GET.get("invitation_id") or request.session.get("invitation_id")


def clear_invite_from_session(request):
    if "invitation_id" in request.session:
        del request.session["invitation_id"]
