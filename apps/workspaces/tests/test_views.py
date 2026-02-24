from django.contrib.auth.models import AnonymousUser

from apps.utils.tests.base import WorkspaceViewTestCase
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
