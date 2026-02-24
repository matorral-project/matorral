from apps.users.models import CustomUser

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

ROLE_CHOICES = (
    (ROLE_ADMIN, "Administrator"),
    (ROLE_MEMBER, "Member"),
)


def is_member(user: CustomUser, workspace) -> bool:
    if not workspace:
        return False
    return workspace.members.filter(id=user.id).exists()


def is_admin(user: CustomUser, workspace) -> bool:
    if not workspace:
        return False

    from .models import Membership

    return Membership.objects.filter(workspace=workspace, user=user, role=ROLE_ADMIN).exists()
