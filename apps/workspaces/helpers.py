from django.utils.translation import gettext as _

from apps.users.models import CustomUser

from .models import Invitation, Membership, Workspace
from .roles import ROLE_ADMIN
from .slugs import get_next_unique_workspace_slug
from .tasks import create_demo_project_task

from allauth.account.models import EmailAddress


def get_default_workspace_name_for_user(user: CustomUser) -> str:
    return (user.get_display_name().split("@")[0] or _("My Workspace")).title()


def get_default_workspace_for_user(user: CustomUser) -> Workspace | None:
    if user.workspaces.exists():
        return user.workspaces.first()
    return None


def create_default_workspace_for_user(user: CustomUser, workspace_name: str | None = None):
    workspace_name = workspace_name or get_default_workspace_name_for_user(user)
    slug = get_next_unique_workspace_slug(workspace_name)
    if not slug:
        slug = get_next_unique_workspace_slug(get_default_workspace_name_for_user(user))
    if not slug:
        slug = get_next_unique_workspace_slug("workspace")
    workspace = Workspace.objects.create(name=workspace_name, slug=slug)
    Membership.objects.create(workspace=workspace, user=user, role=ROLE_ADMIN)
    create_demo_project_task.delay(workspace.pk, user.pk)
    return workspace


def get_open_invitations_for_user(user: CustomUser) -> list[dict]:
    user_emails = list(EmailAddress.objects.filter(user=user).order_by("-primary"))
    if not user_emails:
        return []

    emails = {e.email for e in user_emails}
    open_invitations = (
        Invitation.objects.filter(email__in=list(emails), is_accepted=False)
        .exclude(workspace__membership__user=user)
        .values("id", "workspace__name", "email")
    )
    verified_emails = {email.email for email in user_emails if email.verified}
    return [
        {
            **inv,
            "workspace_name": inv["workspace__name"],
            "verified": inv["email"] in verified_emails,
        }
        for inv in open_invitations
    ]
