from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.utils.tests.base import WorkspaceTestMixin
from apps.workspaces.factories import InvitationFactory, WorkspaceFactory
from apps.workspaces.models import Flag


class TestWorkspaceModel(WorkspaceTestMixin, TestCase):
    """Tests for custom Workspace model properties and methods."""

    def test_email_returns_admin_email(self):
        self.assertEqual(self.workspace.email, self.admin.email)

    def test_email_returns_none_when_no_admin(self):
        workspace = WorkspaceFactory()
        self.assertIsNone(workspace.email)

    def test_pending_invitations_excludes_accepted(self):
        pending = InvitationFactory(workspace=self.workspace, is_accepted=False)
        accepted = InvitationFactory(workspace=self.workspace, is_accepted=True, accepted_by=self.outsider)
        result = list(self.workspace.pending_invitations())
        self.assertIn(pending, result)
        self.assertNotIn(accepted, result)

    def test_sorted_memberships_ordered_by_user_email(self):
        emails = [m.user.email for m in self.workspace.sorted_memberships]
        self.assertEqual(emails, sorted(emails))


class TestFlagIsActive(TestCase):
    """Tests for the custom Flag.is_active() workspace-aware logic."""

    def setUp(self):
        self.flag = Flag.objects.create(name=f"flag-{self._testMethodName}")
        self.workspace = WorkspaceFactory()
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        request.workspace = self.workspace
        self.request = request

    def test_returns_true_when_workspace_in_flag(self):
        self.flag.workspaces.add(self.workspace)
        self.assertTrue(self.flag.is_active(self.request))

    def test_returns_false_when_workspace_not_associated(self):
        self.assertFalse(self.flag.is_active(self.request))

    def test_returns_falsy_when_no_workspace_on_request(self):
        self.flag.workspaces.add(self.workspace)
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        # No workspace attribute — is_active returns None implicitly
        self.assertFalse(self.flag.is_active(request))

    def test_short_circuits_when_parent_returns_true(self):
        self.flag.everyone = True
        self.flag.save()
        # workspace is NOT in the flag, but parent short-circuits and returns True
        self.assertTrue(self.flag.is_active(self.request))
