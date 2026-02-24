from apps.users.factories import CustomUserFactory
from apps.workspaces.models import Invitation, Membership, Workspace
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER

import factory


class WorkspaceFactory(factory.django.DjangoModelFactory):
    """Factory for creating Workspace instances."""

    class Meta:
        model = Workspace

    name = factory.Sequence(lambda n: f"Workspace {n}")
    slug = factory.Sequence(lambda n: f"workspace-{n}")
    description = ""


class MembershipFactory(factory.django.DjangoModelFactory):
    """Factory for creating Membership instances."""

    class Meta:
        model = Membership

    workspace = factory.SubFactory(WorkspaceFactory)
    user = factory.SubFactory(CustomUserFactory)
    role = ROLE_MEMBER


class WorkspaceWithAdminFactory(WorkspaceFactory):
    """Factory for creating a Workspace with an admin member."""

    @factory.post_generation
    def admin(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            MembershipFactory(workspace=self, user=extracted, role=ROLE_ADMIN)
        else:
            MembershipFactory(workspace=self, role=ROLE_ADMIN)


class InvitationFactory(factory.django.DjangoModelFactory):
    """Factory for creating Invitation instances."""

    class Meta:
        model = Invitation

    workspace = factory.SubFactory(WorkspaceFactory)
    email = factory.LazyAttribute(lambda obj: f"invited-{obj.workspace.slug}@example.com")
    role = ROLE_MEMBER
    invited_by = factory.SubFactory(CustomUserFactory)
    is_accepted = False
