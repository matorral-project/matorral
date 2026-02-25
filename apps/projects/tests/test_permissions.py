from django.test import Client, TestCase
from django.urls import reverse

from apps.projects.factories import ProjectFactory
from apps.projects.models import Project, ProjectStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER


class ProjectPermissionTestCase(TestCase):
    """Base test case providing common fixtures for permission tests."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.admin = UserFactory()
        cls.member = UserFactory()
        cls.outsider = UserFactory()

        MembershipFactory(workspace=cls.workspace, user=cls.admin, role=ROLE_ADMIN)
        MembershipFactory(workspace=cls.workspace, user=cls.member, role=ROLE_MEMBER)

        cls.project = ProjectFactory(workspace=cls.workspace, name="Test Project")

    def _get_list_url(self):
        return reverse(
            "projects:project_list",
            kwargs={"workspace_slug": self.workspace.slug},
        )

    def _get_detail_url(self, project=None):
        project = project or self.project
        return reverse(
            "projects:project_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def _get_create_url(self):
        return reverse(
            "projects:project_create",
            kwargs={"workspace_slug": self.workspace.slug},
        )

    def _get_update_url(self, project=None):
        project = project or self.project
        return reverse(
            "projects:project_update",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def _get_delete_url(self, project=None):
        project = project or self.project
        return reverse(
            "projects:project_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def _get_bulk_delete_url(self):
        return reverse(
            "projects:projects_bulk_delete",
            kwargs={"workspace_slug": self.workspace.slug},
        )

    def _get_bulk_status_url(self):
        return reverse(
            "projects:projects_bulk_status",
            kwargs={"workspace_slug": self.workspace.slug},
        )


class AuthenticationTest(ProjectPermissionTestCase):
    """Tests that unauthenticated users are redirected to login."""

    def test_unauthenticated_user_redirected_to_login_list(self):
        response = Client().get(self._get_list_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_detail(self):
        response = Client().get(self._get_detail_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_create(self):
        response = Client().get(self._get_create_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_update(self):
        response = Client().get(self._get_update_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_delete(self):
        response = Client().get(self._get_delete_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_bulk_delete(self):
        response = Client().post(self._get_bulk_delete_url(), {"projects": [self.project.key]})

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_user_redirected_to_login_bulk_status(self):
        response = Client().post(
            self._get_bulk_status_url(),
            {"projects": [self.project.key], "status": ProjectStatus.ACTIVE},
        )

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)


class WorkspaceMembershipTest(ProjectPermissionTestCase):
    """Tests that non-workspace members cannot access project views."""

    def test_non_workspace_member_cannot_access_list(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.get(self._get_list_url())

        self.assertEqual(404, response.status_code)

    def test_non_workspace_member_cannot_access_detail(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.get(self._get_detail_url())

        self.assertEqual(404, response.status_code)

    def test_non_workspace_member_cannot_access_create(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.get(self._get_create_url())

        self.assertEqual(404, response.status_code)

    def test_non_workspace_member_cannot_access_update(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.get(self._get_update_url())

        self.assertEqual(404, response.status_code)

    def test_non_workspace_member_cannot_access_delete(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.get(self._get_delete_url())

        self.assertEqual(404, response.status_code)

    def test_non_workspace_member_cannot_bulk_delete(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.post(self._get_bulk_delete_url(), {"projects": [self.project.key]})

        self.assertEqual(404, response.status_code)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_non_workspace_member_cannot_bulk_status(self):
        client = Client()
        client.force_login(self.outsider)

        response = client.post(
            self._get_bulk_status_url(),
            {"projects": [self.project.key], "status": ProjectStatus.ACTIVE},
        )

        self.assertEqual(404, response.status_code)
        self.project.refresh_from_db()
        self.assertEqual(ProjectStatus.DRAFT, self.project.status)


class WorkspaceMemberAccessTest(ProjectPermissionTestCase):
    """Tests that workspace members can access project views."""

    def test_workspace_member_can_access_list(self):
        client = Client()
        client.force_login(self.member)

        response = client.get(self._get_list_url())

        self.assertEqual(200, response.status_code)

    def test_workspace_member_can_access_detail(self):
        client = Client()
        client.force_login(self.member)

        response = client.get(self._get_detail_url())

        self.assertEqual(200, response.status_code)

    def test_workspace_member_can_create_project(self):
        client = Client()
        client.force_login(self.member)

        response = client.post(
            self._get_create_url(),
            {"name": "New Project", "status": ProjectStatus.DRAFT, "description": ""},
        )

        # Successful create redirects to detail page
        self.assertEqual(302, response.status_code)
        self.assertTrue(Project.objects.filter(name="New Project").exists())

    def test_workspace_member_can_update_project(self):
        client = Client()
        client.force_login(self.member)

        response = client.post(
            self._get_update_url(),
            {
                "name": "Updated Name",
                "status": ProjectStatus.ACTIVE,
                "description": "Updated",
            },
        )

        # Successful update redirects to detail page
        self.assertEqual(302, response.status_code)
        self.project.refresh_from_db()
        self.assertEqual("Updated Name", self.project.name)

    def test_workspace_member_can_delete_project(self):
        client = Client()
        client.force_login(self.member)
        project_pk = self.project.pk

        response = client.post(self._get_delete_url())

        # Successful delete redirects to list page
        self.assertEqual(302, response.status_code)
        self.assertFalse(Project.objects.filter(pk=project_pk).exists())


class WorkspaceIsolationTest(TestCase):
    """Tests that users cannot access projects in other workspaces."""

    @classmethod
    def setUpTestData(cls):
        # Workspace 1 with member and project
        cls.workspace1 = WorkspaceFactory()
        cls.user1 = UserFactory()
        MembershipFactory(workspace=cls.workspace1, user=cls.user1, role=ROLE_MEMBER)
        cls.project1 = ProjectFactory(workspace=cls.workspace1, name="Workspace 1 Project")

        # Workspace 2 with member and project
        cls.workspace2 = WorkspaceFactory()
        cls.user2 = UserFactory()
        MembershipFactory(workspace=cls.workspace2, user=cls.user2, role=ROLE_MEMBER)
        cls.project2 = ProjectFactory(workspace=cls.workspace2, name="Workspace 2 Project")

    def test_cannot_access_project_in_other_teams_workspace(self):
        """User from workspace1 cannot view project in workspace2."""
        client = Client()
        client.force_login(self.user1)

        url = reverse(
            "projects:project_detail",
            kwargs={
                "workspace_slug": self.workspace2.slug,
                "key": self.project2.key,
            },
        )
        response = client.get(url)

        self.assertEqual(404, response.status_code)

    def test_cannot_modify_project_in_other_teams_workspace(self):
        """User from workspace1 cannot update project in workspace2."""
        client = Client()
        client.force_login(self.user1)

        url = reverse(
            "projects:project_update",
            kwargs={
                "workspace_slug": self.workspace2.slug,
                "key": self.project2.key,
            },
        )
        response = client.post(url, {"name": "Hacked!", "status": ProjectStatus.ACTIVE, "description": ""})

        self.assertEqual(404, response.status_code)
        self.project2.refresh_from_db()
        self.assertEqual("Workspace 2 Project", self.project2.name)

    def test_cannot_delete_project_in_other_teams_workspace(self):
        """User from workspace1 cannot delete project in workspace2."""
        client = Client()
        client.force_login(self.user1)

        url = reverse(
            "projects:project_delete",
            kwargs={
                "workspace_slug": self.workspace2.slug,
                "key": self.project2.key,
            },
        )
        response = client.post(url)

        self.assertEqual(404, response.status_code)
        self.assertTrue(Project.objects.filter(pk=self.project2.pk).exists())

    def test_project_list_only_shows_workspace_projects(self):
        """Project list only shows projects from the current workspace."""
        client = Client()
        client.force_login(self.user1)

        url = reverse(
            "projects:project_list",
            kwargs={"workspace_slug": self.workspace1.slug},
        )
        response = client.get(url)

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Workspace 1 Project")
        self.assertNotContains(response, "Workspace 2 Project")
