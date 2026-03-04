from apps.users.models import User

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

ROLE_CHOICES = (
    (ROLE_ADMIN, "Administrator"),
    (ROLE_MEMBER, "Member"),
)


def is_member(user: User, workspace) -> bool:
    if not workspace:
        return False

    return workspace.members.filter(id=user.id).exists()


def is_admin(user: User, workspace) -> bool:
    if not workspace:
        return False

    return user.workspace_memberships.filter(workspace=workspace, role=ROLE_ADMIN).exists()
