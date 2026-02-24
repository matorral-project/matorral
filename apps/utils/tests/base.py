from django.http import Http404
from django.test import TestCase

from apps.users.factories import CustomUserFactory
from apps.utils.tests.utils import call_view_with_middleware
from apps.workspaces.factories import MembershipFactory as WorkspaceMembershipFactory
from apps.workspaces.factories import WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN as WORKSPACE_ROLE_ADMIN
from apps.workspaces.roles import ROLE_MEMBER as WORKSPACE_ROLE_MEMBER


class WorkspaceTestMixin:
    """
    Mixin providing pre-configured workspace and users for tests.

    Provides:
        - workspace: A workspace instance
        - admin: A user with admin role on the workspace
        - member: A user with member role on the workspace
        - outsider: A user not belonging to the workspace
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._create_workspace_fixtures()

    @classmethod
    def _create_workspace_fixtures(cls):
        """Create standard workspace fixtures."""
        cls.workspace = WorkspaceFactory()

        cls.admin = CustomUserFactory()
        cls.member = CustomUserFactory()
        cls.outsider = CustomUserFactory()

        cls.admin_membership = WorkspaceMembershipFactory(
            workspace=cls.workspace, user=cls.admin, role=WORKSPACE_ROLE_ADMIN
        )
        cls.member_membership = WorkspaceMembershipFactory(
            workspace=cls.workspace, user=cls.member, role=WORKSPACE_ROLE_MEMBER
        )


class ViewTestMixin:
    """
    Mixin providing common view testing utilities.
    """

    def assertViewReturns200(self, view_cls, user, workspace_slug=None, **kwargs):
        """Assert that a view returns 200 for the given user."""
        response = call_view_with_middleware(view_cls, user, workspace_slug, **kwargs)
        self.assertEqual(200, response.status_code)
        return response

    def assertViewRedirectsToLogin(self, view_cls, user, workspace_slug=None, **kwargs):
        """Assert that a view redirects to login for the given user."""
        response = call_view_with_middleware(view_cls, user, workspace_slug, **kwargs)
        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)
        return response

    def assertViewReturns404(self, view_cls, user, workspace_slug=None, **kwargs):
        """Assert that a view raises Http404 for the given user."""
        with self.assertRaises(Http404):
            call_view_with_middleware(view_cls, user, workspace_slug, **kwargs)


class WorkspaceViewTestCase(WorkspaceTestMixin, ViewTestMixin, TestCase):
    """Base test case for testing workspace-based views."""

    pass
