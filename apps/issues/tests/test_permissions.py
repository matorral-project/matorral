from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory
from apps.projects.factories import ProjectFactory
from apps.users.factories import CustomUserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER


class IssuePermissionsTest(TestCase):
    """Tests for issue view permissions."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

        cls.admin = CustomUserFactory()
        cls.member = CustomUserFactory()
        cls.outsider = CustomUserFactory()

        MembershipFactory(workspace=cls.workspace, user=cls.admin, role=ROLE_ADMIN)
        MembershipFactory(workspace=cls.workspace, user=cls.member, role=ROLE_MEMBER)

        cls.epic = EpicFactory(project=cls.project)

    def setUp(self):
        self.client = Client()

    def _get_detail_url(self):
        return reverse(
            "issues:issue_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": self.epic.key,
            },
        )

    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated users are redirected to login."""
        response = self.client.get(self._get_detail_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_admin_can_access_detail(self):
        """Workspace admin can access issue detail."""
        self.client.force_login(self.admin)
        response = self.client.get(self._get_detail_url())

        self.assertEqual(200, response.status_code)

    def test_member_can_access_detail(self):
        """Workspace member can access issue detail."""
        self.client.force_login(self.member)
        response = self.client.get(self._get_detail_url())

        self.assertEqual(200, response.status_code)

    def test_outsider_cannot_access_detail(self):
        """Non-workspace member gets 404 for detail view."""
        self.client.force_login(self.outsider)
        response = self.client.get(self._get_detail_url())

        self.assertEqual(404, response.status_code)


class WorkspaceIsolationTest(TestCase):
    """Tests for workspace isolation of issues."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project1 = ProjectFactory(workspace=cls.workspace)
        cls.project2 = ProjectFactory(workspace=cls.workspace)

        cls.user = CustomUserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

        cls.epic1 = EpicFactory(project=cls.project1)
        cls.epic2 = EpicFactory(project=cls.project2)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_issue_in_different_project_returns_404(self):
        """Accessing issue from wrong project returns 404."""
        response = self.client.get(
            reverse(
                "issues:issue_detail",
                kwargs={
                    "workspace_slug": self.workspace.slug,
                    "project_key": self.project1.key,
                    "key": self.epic2.key,  # Wrong project's issue
                },
            )
        )

        self.assertEqual(404, response.status_code)
