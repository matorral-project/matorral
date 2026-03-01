from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.users.factories import UserFactory
from apps.utils.tests.base import WorkspaceTestMixin, WorkspaceViewTestCase
from apps.workspaces.factories import InvitationFactory, MembershipFactory, WorkspaceFactory
from apps.workspaces.models import Invitation, Membership, Workspace
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER
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

    def test_accept_invitation_get_shows_form_for_anonymous_user(self):
        invitation = InvitationFactory(workspace=self.workspace)
        url = reverse("workspaces:accept_invitation", args=[invitation.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, invitation.workspace.name)

    def test_accept_invitation_post_unauthenticated_redirects_to_login(self):
        invitation = InvitationFactory(workspace=self.workspace)
        url = reverse("workspaces:accept_invitation", args=[invitation.id])
        response = self.client.post(url)
        self.assertRedirects(response, reverse("account_login"), fetch_redirect_response=False)

    def test_accept_already_accepted_invitation_post_redirects_with_error(self):
        invitation = InvitationFactory(
            workspace=self.workspace, email=self.outsider.email, is_accepted=True, accepted_by=self.outsider
        )
        self.client.force_login(self.outsider)
        url = reverse("workspaces:accept_invitation", args=[invitation.id])
        response = self.client.post(url)
        self.assertRedirects(response, reverse("landing_pages:home"), fetch_redirect_response=False)

    def test_resend_invitation_sends_email(self):
        invitation = InvitationFactory(workspace=self.workspace)
        self.client.force_login(self.admin)
        url = reverse("workspaces:resend_invitation", args=[self.workspace.slug, invitation.id])
        with patch("apps.workspaces.views.send_invitation") as mock_send:
            response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once_with(invitation)

    def test_cancel_invitation_deletes_it(self):
        invitation = InvitationFactory(workspace=self.workspace)
        self.client.force_login(self.admin)
        url = reverse("workspaces:cancel_invitation", args=[self.workspace.slug, invitation.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())


class TestWorkspaceHomeView(WorkspaceTestMixin, TestCase):
    def test_get_returns_200_for_member(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:home", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_includes_workspace_in_context(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:home", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.context["workspace"], self.workspace)

    def test_anonymous_user_redirected_to_login(self):
        url = reverse("workspaces:home", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


class TestDismissOnboardingView(WorkspaceTestMixin, TestCase):
    def test_post_sets_onboarding_completed(self):
        self.admin.onboarding_completed = False
        self.admin.save()
        self.client.force_login(self.admin)
        url = reverse("workspaces:dismiss_onboarding", args=[self.workspace.slug])
        self.client.post(url)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.onboarding_completed)

    def test_post_returns_hx_redirect(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:dismiss_onboarding", args=[self.workspace.slug])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)

    def test_get_returns_405(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:dismiss_onboarding", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


class TestManageWorkspacesView(WorkspaceTestMixin, TestCase):
    def test_get_returns_200_for_logged_in_user(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspaces")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_includes_workspaces_in_context(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspaces")
        response = self.client.get(url)
        self.assertIn(self.workspace, response.context["workspaces"])

    def test_anonymous_user_redirected_to_login(self):
        url = reverse("workspaces:manage_workspaces")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)


class TestCreateWorkspaceView(WorkspaceTestMixin, TestCase):
    def test_get_returns_200(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_post_creates_workspace_and_redirects(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        response = self.client.post(url, {"name": "Brand New Workspace"})
        self.assertTrue(Workspace.objects.filter(name="Brand New Workspace").exists())
        self.assertRedirects(response, reverse("workspaces:manage_workspaces"), fetch_redirect_response=False)

    def test_post_creates_admin_membership_for_creator(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        self.client.post(url, {"name": "Another Workspace"})
        workspace = Workspace.objects.get(name="Another Workspace")
        self.assertTrue(Membership.objects.filter(workspace=workspace, user=self.admin, role=ROLE_ADMIN).exists())

    def test_post_invalid_slug_returns_form_with_errors(self):
        # Use a duplicate slug to trigger model-level unique validation
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        response = self.client.post(url, {"name": "Duplicate Slug Workspace", "slug": self.workspace.slug})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Workspace.objects.filter(name="Duplicate Slug Workspace").exists())

    def test_htmx_post_returns_hx_redirect_on_success(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        response = self.client.post(url, {"name": "HTMX Workspace"}, headers={"HX-Request": "true"})
        self.assertIn("HX-Redirect", response)

    def test_htmx_post_invalid_returns_form_fragment(self):
        # Use a duplicate slug to trigger model-level unique validation
        self.client.force_login(self.admin)
        url = reverse("workspaces:create_workspace")
        response = self.client.post(
            url, {"name": "Another Duplicate", "slug": self.workspace.slug}, headers={"HX-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)


class TestManageWorkspaceViewExtra(WorkspaceTestMixin, TestCase):
    def test_get_returns_200_for_admin(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_returns_200_for_member(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_admin_update_with_slug_change_redirects(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        response = self.client.post(url, {"name": "Renamed Workspace", "slug": "new-slug"})
        self.assertRedirects(
            response,
            reverse("workspaces:manage_workspace", args=["new-slug"]),
            fetch_redirect_response=False,
        )

    def test_member_form_fields_are_disabled(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:manage_workspace", args=[self.workspace.slug])
        response = self.client.get(url)
        form = response.context["workspace_form"]
        for field in form.fields.values():
            self.assertTrue(field.disabled)


class TestManageWorkspaceMembersView(WorkspaceTestMixin, TestCase):
    def test_get_returns_200(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspace_members", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_includes_pending_invitations_in_context(self):
        invitation = InvitationFactory(workspace=self.workspace)
        self.client.force_login(self.admin)
        url = reverse("workspaces:manage_workspace_members", args=[self.workspace.slug])
        response = self.client.get(url)
        self.assertIn(invitation, response.context["pending_invitations"])


class TestWorkspaceMembershipDetailsView(WorkspaceTestMixin, TestCase):
    def test_get_returns_200_for_self(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_returns_200_for_admin_viewing_member(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_outsider_redirected_when_accessing_other_membership(self):
        self.client.force_login(self.outsider)
        # outsider is not in workspace, so middleware returns 404 before we check membership
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_member_cannot_access_other_members_details(self):
        other_member = UserFactory()
        other_membership = MembershipFactory(workspace=self.workspace, user=other_member, role=ROLE_MEMBER)
        self.client.force_login(self.member)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, other_membership.pk])
        response = self.client.get(url)
        self.assertRedirects(
            response,
            reverse("workspaces:manage_workspace_members", args=[self.workspace.slug]),
            fetch_redirect_response=False,
        )

    def test_admin_can_change_member_role(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        self.client.post(url, {"role": ROLE_ADMIN})
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, ROLE_ADMIN)

    def test_admin_cannot_change_own_role(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.admin_membership.pk])
        self.client.post(url, {"role": ROLE_MEMBER})
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, ROLE_ADMIN)

    def test_self_form_fields_are_disabled(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.get(url)
        self.assertTrue(response.context["editing_self"])

    def test_member_post_to_own_membership_returns_403(self):
        # Non-admin member posting to their own page gets 403 (can access but can't change roles)
        self.client.force_login(self.member)
        url = reverse("workspaces:workspace_membership_details", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.post(url, {"role": ROLE_ADMIN})
        self.assertEqual(response.status_code, 403)


class TestRemoveWorkspaceMembershipView(WorkspaceTestMixin, TestCase):
    def test_admin_can_remove_member(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:remove_workspace_membership", args=[self.workspace.slug, self.member_membership.pk])
        self.client.post(url)
        self.assertFalse(Membership.objects.filter(pk=self.member_membership.pk).exists())

    def test_member_can_remove_self(self):
        self.client.force_login(self.member)
        url = reverse("workspaces:remove_workspace_membership", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.post(url)
        self.assertFalse(Membership.objects.filter(pk=self.member_membership.pk).exists())
        self.assertRedirects(response, reverse("landing_pages:home"), fetch_redirect_response=False)

    def test_member_cannot_remove_other_members(self):
        other_member = UserFactory()
        other_membership = MembershipFactory(workspace=self.workspace, user=other_member, role=ROLE_MEMBER)
        self.client.force_login(self.member)
        url = reverse("workspaces:remove_workspace_membership", args=[self.workspace.slug, other_membership.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Membership.objects.filter(pk=other_membership.pk).exists())

    def test_cannot_remove_last_admin(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:remove_workspace_membership", args=[self.workspace.slug, self.admin_membership.pk])
        self.client.post(url)
        self.assertTrue(Membership.objects.filter(pk=self.admin_membership.pk).exists())

    def test_admin_redirect_after_removing_member(self):
        self.client.force_login(self.admin)
        url = reverse("workspaces:remove_workspace_membership", args=[self.workspace.slug, self.member_membership.pk])
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("workspaces:manage_workspace_members", args=[self.workspace.slug]),
            fetch_redirect_response=False,
        )
