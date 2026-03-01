from django.test import TestCase

from apps.users.factories import UserFactory
from apps.workspaces.factories import InvitationFactory, MembershipFactory, WorkspaceFactory
from apps.workspaces.forms import InvitationForm, WorkspaceSignupForm
from apps.workspaces.roles import ROLE_ADMIN


class TestWorkspaceSignupFormInvitationEmailValidation(TestCase):
    def test_mismatched_invitation_email_raises_validation_error(self):
        workspace = WorkspaceFactory()
        invitation = InvitationFactory(workspace=workspace, email="invited@example.com")

        form = WorkspaceSignupForm(
            data={
                "email": "different@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "terms_agreement": True,
                "invitation_id": str(invitation.id),
                "workspace_name": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "You must sign up with the email address that the invitation was sent to.",
            str(form.errors),
        )


class TestInvitationFormEmailValidation(TestCase):
    def setUp(self):
        self.workspace = WorkspaceFactory()
        admin = UserFactory()
        MembershipFactory(workspace=self.workspace, user=admin, role=ROLE_ADMIN)

    def test_existing_member_email_raises_validation_error(self):
        member = UserFactory(email="member@example.com")
        MembershipFactory(workspace=self.workspace, user=member)

        form = InvitationForm(self.workspace, data={"email": "member@example.com", "role": "member"})
        self.assertFalse(form.is_valid())
        self.assertIn("is already a member of this workspace", str(form.errors))

    def test_pending_invitation_email_raises_validation_error(self):
        InvitationFactory(workspace=self.workspace, email="pending@example.com")

        form = InvitationForm(self.workspace, data={"email": "pending@example.com", "role": "member"})
        self.assertFalse(form.is_valid())
        self.assertIn("There is already a pending invitation", str(form.errors))
