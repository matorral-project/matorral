from django.conf import settings
from django.test import RequestFactory, TestCase

from apps.users.factories import UserFactory
from apps.workspaces.adapter import AcceptInvitationAdapter
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_MEMBER


class TestGetLoginRedirectUrl(TestCase):
    def setUp(self):
        self.adapter = AcceptInvitationAdapter()
        self.request = RequestFactory().get("/accounts/login/")
        self.request.session = {}

    def test_redirects_to_workspace_when_user_has_one(self):
        user = UserFactory()
        workspace = WorkspaceFactory()
        MembershipFactory(workspace=workspace, user=user, role=ROLE_MEMBER)
        self.request.user = user

        self.assertEqual(self.adapter.get_login_redirect_url(self.request), workspace.get_absolute_url())

    def test_falls_back_to_login_redirect_url_without_workspace(self):
        self.request.user = UserFactory()

        self.assertEqual(self.adapter.get_login_redirect_url(self.request), settings.LOGIN_REDIRECT_URL)
