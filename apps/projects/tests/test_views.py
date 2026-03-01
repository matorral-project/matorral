from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.projects.factories import ProjectFactory
from apps.projects.models import Project, ProjectStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_MEMBER


class ProjectViewTestCase(TestCase):
    """Base test case providing common fixtures for view tests."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_MEMBER)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_list_url(self):
        return reverse(
            "projects:project_list",
            kwargs={"workspace_slug": self.workspace.slug},
        )

    def _get_detail_url(self, project):
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

    def _get_update_url(self, project):
        return reverse(
            "projects:project_update",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def _get_delete_url(self, project):
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


class ProjectListViewTest(ProjectViewTestCase):
    """Tests for ProjectListView functionality."""

    def test_list_view_shows_projects(self):
        ProjectFactory(workspace=self.workspace, name="My Project")

        response = self.client.get(self._get_list_url())

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "My Project")

    def test_list_view_paginates_at_default_page_size(self):
        for i in range(settings.DEFAULT_PAGE_SIZE + 5):
            ProjectFactory(workspace=self.workspace, name=f"Project {i:02d}")

        response = self.client.get(self._get_list_url())

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(settings.DEFAULT_PAGE_SIZE, len(response.context["projects"]))

    def test_list_view_second_page(self):
        total_items = settings.DEFAULT_PAGE_SIZE + 5
        for i in range(total_items):
            ProjectFactory(workspace=self.workspace, name=f"Project {i:02d}")

        response = self.client.get(self._get_list_url() + "?page=2")

        self.assertEqual(200, response.status_code)
        self.assertEqual(total_items - settings.DEFAULT_PAGE_SIZE, len(response.context["projects"]))

    def test_list_view_search_filter(self):
        ProjectFactory(workspace=self.workspace, name="Alpha Project")
        ProjectFactory(workspace=self.workspace, name="Beta Project")

        response = self.client.get(self._get_list_url() + "?search=Alpha")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Alpha Project")
        self.assertNotContains(response, "Beta Project")

    def test_list_view_status_filter(self):
        ProjectFactory(workspace=self.workspace, name="Draft Project", status=ProjectStatus.DRAFT)
        ProjectFactory(workspace=self.workspace, name="Active Project", status=ProjectStatus.ACTIVE)

        response = self.client.get(self._get_list_url() + "?status=active")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Active Project")
        self.assertNotContains(response, "Draft Project")

    def test_list_view_multi_status_filter(self):
        """Multi-select status filter should return projects matching any selected status."""
        ProjectFactory(workspace=self.workspace, name="Draft Project", status=ProjectStatus.DRAFT)
        ProjectFactory(workspace=self.workspace, name="Active Project", status=ProjectStatus.ACTIVE)
        ProjectFactory(
            workspace=self.workspace,
            name="Completed Project",
            status=ProjectStatus.COMPLETED,
        )

        response = self.client.get(self._get_list_url() + "?status=draft,active")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Draft Project")
        self.assertContains(response, "Active Project")
        self.assertNotContains(response, "Completed Project")

    def test_list_view_status_filter_ignores_invalid_values(self):
        """Invalid values in comma-separated status filter should be ignored."""
        ProjectFactory(workspace=self.workspace, name="Active Project", status=ProjectStatus.ACTIVE)
        ProjectFactory(workspace=self.workspace, name="Draft Project", status=ProjectStatus.DRAFT)

        response = self.client.get(self._get_list_url() + "?status=active,invalid,bogus")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Active Project")
        self.assertNotContains(response, "Draft Project")

    def test_list_view_lead_filter(self):
        other_user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user, role=ROLE_MEMBER)
        ProjectFactory(workspace=self.workspace, name="My Lead Project", lead=self.user)
        ProjectFactory(workspace=self.workspace, name="Other Lead Project", lead=other_user)

        response = self.client.get(self._get_list_url() + f"?lead={self.user.pk}")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "My Lead Project")
        self.assertNotContains(response, "Other Lead Project")

    def test_list_view_lead_filter_none(self):
        ProjectFactory(workspace=self.workspace, name="Has Lead", lead=self.user)
        ProjectFactory(workspace=self.workspace, name="No Lead", lead=None)

        response = self.client.get(self._get_list_url() + "?lead=none")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "No Lead")
        self.assertNotContains(response, "Has Lead")

    def test_list_view_group_by_status_disables_pagination(self):
        for i in range(20):
            ProjectFactory(workspace=self.workspace, name=f"Project {i:02d}")

        response = self.client.get(self._get_list_url() + "?group_by=status")

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context["is_paginated"])
        self.assertIn("grouped_projects", response.context)

    def test_list_view_htmx_returns_partial(self):
        ProjectFactory(workspace=self.workspace, name="Test Project")

        response = self.client.get(self._get_list_url(), HTTP_HX_REQUEST="true", HTTP_HX_TARGET="page-content")

        self.assertEqual(200, response.status_code)
        # Should not include full HTML structure
        self.assertNotContains(response, "<!DOCTYPE html>")


class ProjectDetailViewTest(ProjectViewTestCase):
    """Tests for ProjectDetailView functionality."""

    def test_detail_view_shows_project(self):
        project = ProjectFactory(
            workspace=self.workspace,
            name="Test Project",
            description="Test description",
        )

        response = self.client.get(self._get_detail_url(project))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Test Project")
        self.assertContains(response, "Test description")

    def test_detail_view_nonexistent_key_returns_404(self):
        project = ProjectFactory(workspace=self.workspace)
        url = self._get_detail_url(project).replace(project.key, "NOTFND")

        response = self.client.get(url)

        self.assertEqual(404, response.status_code)


class ProjectCreateViewTest(ProjectViewTestCase):
    """Tests for ProjectCreateView functionality."""

    def test_create_view_shows_form(self):
        response = self.client.get(self._get_create_url())

        self.assertEqual(200, response.status_code)
        self.assertContains(response, 'name="name"')

    def test_create_valid_form_creates_project(self):
        response = self.client.post(
            self._get_create_url(),
            {
                "name": "New Project",
                "status": ProjectStatus.DRAFT,
                "description": "A new project",
            },
        )

        self.assertEqual(302, response.status_code)
        project = Project.objects.get(name="New Project")
        self.assertEqual(self.workspace, project.workspace)
        self.assertEqual("A new project", project.description)

    def test_create_invalid_form_shows_errors(self):
        response = self.client.post(
            self._get_create_url(),
            {"name": "", "status": ProjectStatus.DRAFT},  # Name required
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "This field is required")

    def test_create_shows_success_message(self):
        response = self.client.post(
            self._get_create_url(),
            {"name": "New Project", "status": ProjectStatus.DRAFT, "description": ""},
            follow=True,
        )

        self.assertContains(response, "Project created successfully")

    def test_create_duplicate_key_shows_error(self):
        ProjectFactory(workspace=self.workspace, key="EXIST")

        response = self.client.post(
            self._get_create_url(),
            {
                "name": "New Project",
                "key": "EXIST",
                "status": ProjectStatus.DRAFT,
                "description": "",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "A project with this key already exists")
        self.assertEqual(1, Project.objects.filter(workspace=self.workspace, key="EXIST").count())


class ProjectUpdateViewTest(ProjectViewTestCase):
    """Tests for ProjectUpdateView functionality."""

    def test_update_view_shows_form_with_data(self):
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.get(self._get_update_url(project))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Original Name")

    def test_update_valid_form_updates_project(self):
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_update_url(project),
            {
                "name": "Updated Name",
                "key": project.key,
                "status": ProjectStatus.ACTIVE,
                "description": "Updated",
            },
        )

        self.assertEqual(302, response.status_code)
        project.refresh_from_db()
        self.assertEqual("Updated Name", project.name)
        self.assertEqual(ProjectStatus.ACTIVE, project.status)

    def test_update_invalid_form_shows_errors(self):
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_update_url(project),
            {"name": "", "key": project.key, "status": ProjectStatus.DRAFT},
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "This field is required")

    def test_update_shows_success_message(self):
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_update_url(project),
            {
                "name": "Updated Name",
                "key": project.key,
                "status": ProjectStatus.ACTIVE,
                "description": "",
            },
            follow=True,
        )

        self.assertContains(response, "Project updated successfully")

    def test_update_duplicate_key_shows_error(self):
        existing_project = ProjectFactory(workspace=self.workspace, key="EXIST")
        project = ProjectFactory(workspace=self.workspace, name="My Project")

        response = self.client.post(
            self._get_update_url(project),
            {
                "name": "My Project",
                "key": "EXIST",
                "status": ProjectStatus.DRAFT,
                "description": "",
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "A project with this key already exists")
        project.refresh_from_db()
        self.assertNotEqual("EXIST", project.key)
        self.assertTrue(Project.objects.filter(pk=existing_project.pk, key="EXIST").exists())


class ProjectDeleteViewTest(ProjectViewTestCase):
    """Tests for ProjectDeleteView functionality."""

    def test_delete_view_shows_confirmation(self):
        project = ProjectFactory(workspace=self.workspace, name="To Delete")

        response = self.client.get(self._get_delete_url(project))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "To Delete")

    def test_delete_removes_project_and_redirects(self):
        project = ProjectFactory(workspace=self.workspace)
        project_pk = project.pk

        response = self.client.post(self._get_delete_url(project))

        self.assertEqual(302, response.status_code)
        self.assertIn(self._get_list_url(), response.url)
        self.assertFalse(Project.objects.filter(pk=project_pk).exists())

    def test_delete_shows_success_message(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(self._get_delete_url(project), follow=True)

        self.assertContains(response, "Project deleted successfully")


class ProjectBulkDeleteViewTest(ProjectViewTestCase):
    """Tests for ProjectBulkDeleteView functionality."""

    def test_bulk_delete_removes_selected_projects(self):
        project1 = ProjectFactory(workspace=self.workspace)
        project2 = ProjectFactory(workspace=self.workspace)
        project3 = ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_bulk_delete_url(),
            {"projects": [project1.key, project2.key], "page": 1},
        )

        self.assertEqual(302, response.status_code)
        self.assertFalse(Project.objects.filter(pk=project1.pk).exists())
        self.assertFalse(Project.objects.filter(pk=project2.pk).exists())
        self.assertTrue(Project.objects.filter(pk=project3.pk).exists())

    def test_bulk_delete_empty_selection_shows_warning(self):
        ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_bulk_delete_url(),
            {"projects": [], "page": 1},
            follow=True,
        )

        self.assertContains(response, "No projects selected")

    def test_bulk_delete_invalid_keys_rejected(self):
        project = ProjectFactory(workspace=self.workspace)

        self.client.post(
            self._get_bulk_delete_url(),
            {"projects": ["INVALID-KEY"], "page": 1},
            follow=True,
        )

        self.assertTrue(Project.objects.filter(pk=project.pk).exists())


class ProjectCloneViewTest(ProjectViewTestCase):
    """Tests for ProjectCloneView functionality."""

    def _get_clone_url(self, project):
        return reverse(
            "projects:project_clone",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def test_clone_creates_copy_of_project(self):
        project = ProjectFactory(
            workspace=self.workspace,
            name="Original Project",
            description="Original description",
            status=ProjectStatus.ACTIVE,
            lead=self.user,
        )

        response = self.client.post(self._get_clone_url(project))

        self.assertEqual(302, response.status_code)
        self.assertEqual(2, Project.objects.filter(workspace=self.workspace).count())
        cloned = Project.objects.exclude(pk=project.pk).get()
        self.assertIn("Original Project", cloned.name)
        self.assertIn("Copy", cloned.name)
        self.assertEqual("Original description", cloned.description)
        self.assertEqual(ProjectStatus.ACTIVE, cloned.status)
        self.assertEqual(self.user, cloned.lead)

    def test_clone_generates_new_key(self):
        project = ProjectFactory(workspace=self.workspace, name="Test Project")

        self.client.post(self._get_clone_url(project))

        cloned = Project.objects.exclude(pk=project.pk).get()
        self.assertNotEqual(project.key, cloned.key)

    def test_clone_redirects_to_cloned_project(self):
        project = ProjectFactory(workspace=self.workspace, name="Test Project")

        response = self.client.post(self._get_clone_url(project))

        cloned = Project.objects.exclude(pk=project.pk).get()
        self.assertIn(cloned.key, response.url)

    def test_clone_shows_success_message(self):
        project = ProjectFactory(workspace=self.workspace, name="Test Project")

        response = self.client.post(self._get_clone_url(project), follow=True)

        self.assertContains(response, "Project cloned successfully")

    def test_clone_nonexistent_project_returns_404(self):
        project = ProjectFactory(workspace=self.workspace)
        url = self._get_clone_url(project).replace(project.key, "NOTFND")

        response = self.client.post(url)

        self.assertEqual(404, response.status_code)

    def test_clone_get_method_not_allowed(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_clone_url(project))

        self.assertEqual(405, response.status_code)


class ProjectBulkStatusViewTest(ProjectViewTestCase):
    """Tests for ProjectBulkStatusView functionality."""

    def test_bulk_status_updates_selected_projects(self):
        project1 = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)
        project2 = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(
            self._get_bulk_status_url(),
            {
                "projects": [project1.key, project2.key],
                "status": ProjectStatus.ACTIVE,
                "page": 1,
            },
        )

        self.assertEqual(302, response.status_code)
        project1.refresh_from_db()
        project2.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project1.status)
        self.assertEqual(ProjectStatus.ACTIVE, project2.status)

    def test_bulk_status_invalid_status_shows_error(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"projects": [project.key], "status": "invalid_status", "page": 1},
            follow=True,
        )

        self.assertContains(response, "Invalid status")
        project.refresh_from_db()
        self.assertEqual(ProjectStatus.DRAFT, project.status)

    def test_bulk_status_empty_selection_shows_warning(self):
        response = self.client.post(
            self._get_bulk_status_url(),
            {"projects": [], "status": ProjectStatus.ACTIVE, "page": 1},
            follow=True,
        )

        self.assertContains(response, "No projects selected")


class ProjectRowInlineEditViewTest(ProjectViewTestCase):
    """Tests for the inline edit view for project rows."""

    def _get_inline_edit_url(self, project):
        return reverse(
            "projects:project_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(project))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_row_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("project", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(project) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_row.html")

    def test_post_updates_project_name(self):
        """POST updates the project name."""
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_inline_edit_url(project),
            {
                "name": "Updated Name",
                "status": project.status,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual("Updated Name", project.name)

    def test_post_updates_project_status(self):
        """POST updates the project status."""
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(project),
            {
                "name": project.name,
                "status": ProjectStatus.ACTIVE,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project.status)

    def test_post_updates_project_lead(self):
        """POST updates the project lead."""
        project = ProjectFactory(workspace=self.workspace, lead=None)

        response = self.client.post(
            self._get_inline_edit_url(project),
            {
                "name": project.name,
                "status": project.status,
                "lead": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual(self.user, project.lead)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_inline_edit_url(project),
            {
                "name": "",  # Required field
                "status": project.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_row_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)

    def test_get_with_group_by_hides_column(self):
        """GET with show_status=0 returns template with hidden column."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(project) + "?show_status=0")

        self.assertEqual(200, response.status_code)
        self.assertIn("show_status", response.context)
        self.assertFalse(response.context["show_status"])


class ProjectDetailInlineEditViewTest(ProjectViewTestCase):
    """Tests for the inline edit view for project detail page."""

    def _get_detail_inline_edit_url(self, project):
        return reverse(
            "projects:project_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_inline_edit_url(project))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("project", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_inline_edit_url(project) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_detail_header.html")

    def test_post_updates_project_name(self):
        """POST updates the project name."""
        project = ProjectFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_detail_inline_edit_url(project),
            {
                "name": "Updated Name",
                "status": project.status,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual("Updated Name", project.name)

    def test_post_updates_project_description(self):
        """POST updates the project description."""
        project = ProjectFactory(workspace=self.workspace, description="Original description")

        response = self.client.post(
            self._get_detail_inline_edit_url(project),
            {
                "name": project.name,
                "status": project.status,
                "description": "Updated description",
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual("Updated description", project.description)

    def test_post_updates_project_status(self):
        """POST updates the project status."""
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(
            self._get_detail_inline_edit_url(project),
            {
                "name": project.name,
                "status": ProjectStatus.ACTIVE,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project.status)

    def test_post_updates_project_lead(self):
        """POST updates the project lead."""
        project = ProjectFactory(workspace=self.workspace, lead=None)

        response = self.client.post(
            self._get_detail_inline_edit_url(project),
            {
                "name": project.name,
                "status": project.status,
                "lead": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        project.refresh_from_db()
        self.assertEqual(self.user, project.lead)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_detail_inline_edit_url(project),
            {
                "name": "",  # Required field
                "status": project.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "projects/includes/project_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)


class ProjectBulkMoveViewTest(ProjectViewTestCase):
    """Tests for ProjectBulkMoveView functionality."""

    def setUp(self):
        super().setUp()
        self.target_workspace = WorkspaceFactory()
        MembershipFactory(workspace=self.target_workspace, user=self.user, role=ROLE_MEMBER)

    def _get_bulk_move_url(self):
        return reverse("projects:projects_bulk_move", kwargs={"workspace_slug": self.workspace.slug})

    def test_bulk_move_moves_all_selected_projects(self):
        project1 = ProjectFactory(workspace=self.workspace)
        project2 = ProjectFactory(workspace=self.workspace)

        self.client.post(
            self._get_bulk_move_url(),
            {"projects": [project1.key, project2.key], "workspace": self.target_workspace.pk, "page": 1},
        )

        project1.refresh_from_db()
        project2.refresh_from_db()
        self.assertEqual(self.target_workspace, project1.workspace)
        self.assertEqual(self.target_workspace, project2.workspace)

    def test_bulk_move_shows_success_message(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_bulk_move_url(),
            {"projects": [project.key], "workspace": self.target_workspace.pk, "page": 1},
            follow=True,
        )

        self.assertContains(response, "being moved to")
        self.assertContains(response, self.target_workspace.name)

    def test_bulk_move_empty_selection_shows_warning(self):
        response = self.client.post(
            self._get_bulk_move_url(),
            {"projects": [], "workspace": self.target_workspace.pk, "page": 1},
            follow=True,
        )

        self.assertContains(response, "No projects selected")

    def test_bulk_move_does_not_move_projects_from_other_workspace(self):
        other_workspace = WorkspaceFactory()
        other_project = ProjectFactory(workspace=other_workspace)

        self.client.post(
            self._get_bulk_move_url(),
            {"projects": [other_project.key], "workspace": self.target_workspace.pk, "page": 1},
            follow=True,
        )

        other_project.refresh_from_db()
        self.assertEqual(other_workspace, other_project.workspace)

    def test_bulk_move_get_not_allowed(self):
        response = self.client.get(self._get_bulk_move_url())

        self.assertEqual(405, response.status_code)
