from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.utils.tests.base import WorkspaceTestMixin, WorkspaceViewTestCase
from apps.workspaces.factories import InvitationFactory, MembershipFactory, WorkspaceFactory
from apps.workspaces.models import Invitation, Membership, Workspace
from apps.workspaces.roles import ROLE_ADMIN
from apps.workspaces.views import WorkspaceDetailView


class WorkspaceViewAccessControlTest(WorkspaceViewTestCase):
    def test_anonymous_user_redirects_to_login(self):
        self.assertViewRedirectsToLogin(WorkspaceDetailView, AnonymousUser(), self.workspace.slug)

    def test_workspace_admin_can_access_workspace(self):
        self.assertViewReturns200(WorkspaceDetailView, self.admin, self.workspace.slug)

    def test_workspace_member_can_access_workspace(self):
        self.assertViewReturns200(WorkspaceDetailView, self.member, self.workspace.slug)

    def test_non_workspace_member_cannot_access_workspace(self):
        self.assertViewReturns404(WorkspaceDetailView, self.outsider, self.workspace.slug)

    def test_nonexistent_workspace_returns_404(self):
        self.assertViewReturns404(WorkspaceDetailView, self.admin, "nonexistent")


class TestManageWorkspaceView(WorkspaceTestMixin, TestCase):
    """Tests for manage_workspace and delete_workspace views."""

    def test_admin_can_update_workspace_name(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        self.client.post(url, {"name": "New Name"})
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, "New Name")

    def test_member_cannot_update_workspace(self):
        original_name = self.workspace.name
        self.client.force_login(self.member)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        self.client.post(url, {"name": "Hacked Name"})
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.name, original_name)

    def test_delete_workspace_leaves_user_when_others_exist(self):
        second_workspace = WorkspaceFactory()
        MembershipFactory(workspace=second_workspace, user=self.admin, role=ROLE_ADMIN)
        self.client.force_login(self.admin)
        url = reverse("workspaces:delete_workspace", args=[self.workspace.slug])
        self.client.post(url)
        self.assertFalse(Workspace.objects.filter(pk=self.workspace.pk).exists())
        self.assertTrue(self.admin.__class__.objects.filter(pk=self.admin.pk).exists())

    def test_cannot_delete_only_workspace_without_flag(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:delete_workspace", args=[self.workspace.slug])
        self.client.post(url)
        self.assertTrue(Workspace.objects.filter(pk=self.workspace.pk).exists())

    def test_delete_only_workspace_with_flag_removes_user_and_workspace(self):
        admin_pk = self.admin.pk
        self.client.force_login(self.admin)
        url = reverse("workspaces:delete_workspace", args=[self.workspace.slug])
        self.client.post(url, {"delete_account": "1"})
        self.assertFalse(Workspace.objects.filter(pk=self.workspace.pk).exists())
        self.assertFalse(self.admin.__class__.objects.filter(pk=admin_pk).exists())


class TestInvitationViews(WorkspaceTestMixin, TestCase):
    """Tests for send_invitation_view and accept_invitation views."""

    @patch("apps.workspaces.views.send_invitation")
    def test_send_invitation_creates_invitation_and_sends_email(self, mock_send):
        self.client.force_login(self.admin)
        url = reverse("workspaces:send_invitation", args=[self.workspace.slug])
        self.client.post(url, {"email": "new@example.com", "role": "member"})
        self.assertTrue(Invitation.objects.filter(workspace=self.workspace, email="new@example.com").exists())
        mock_send.assert_called_once()

    def test_non_admin_cannot_send_invitation(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:send_invitation", args=[self.workspace.slug])
        response = self.client.post(url, {"email": "new@example.com", "role": "member"})
        self.assertEqual(response.status_code, 404)

    def test_duplicate_email_does_not_create_second_invitation(self):
        InvitationFactory(workspace=self.workspace, email="dupe@example.com")
        self.client.force_login(self.admin)
        url = reverse("workspaces:send_invitation", args=[self.workspace.slug])
        self.client.post(url, {"email": "dupe@example.com", "role": "member"})
        self.assertEqual(Invitation.objects.filter(workspace=self.workspace, email="dupe@example.com").count(), 1)

    @override_settings(
        FREE_TIER_LIMITS={
            "MAX_MEMBERS_PER_WORKSPACE": 1,
            "MAX_INVITATIONS_PER_WEEK": 100,
            "MAX_WORK_ITEMS_PER_WORKSPACE": 1000,
        }
    )
    def test_member_limit_prevents_invitation(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:send_invitation", args=[self.workspace.slug])
        self.client.post(url, {"email": "new@example.com", "role": "member"})
        self.assertFalse(Invitation.objects.filter(workspace=self.workspace, email="new@example.com").exists())

    @override_settings(
        FREE_TIER_LIMITS={
            "MAX_MEMBERS_PER_WORKSPACE": 10,
            "MAX_INVITATIONS_PER_WEEK": 0,
            "MAX_WORK_ITEMS_PER_WORKSPACE": 1000,
        }
    )
    def test_invitation_limit_prevents_invitation(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:send_invitation", args=[self.workspace.slug])
        self.client.post(url, {"email": "new@example.com", "role": "member"})
        self.assertFalse(Invitation.objects.filter(workspace=self.workspace, email="new@example.com").exists())

    def test_accept_invitation_redirects_existing_member(self):
        invitation = InvitationFactory(workspace=self.workspace)
        self.client.force_login(self.member)
        url = reverse("workspaces:accept_invitation", args=[invitation.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_accept_invitation_post_adds_user_to_workspace(self):
        invitation = InvitationFactory(workspace=self.workspace, email=self.outsider.email)
        self.client.force_login(self.outsider)
        url = reverse("workspaces:accept_invitation", args=[invitation.id])
        self.client.post(url)
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_accepted)
        self.assertTrue(Membership.objects.filter(workspace=self.workspace, user=self.outsider).exists())
