import json

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, MilestoneFactory, StoryFactory
from apps.issues.models import IssueStatus
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
            "projects:project_bulk_action",
            kwargs={"workspace_slug": self.workspace.slug, "action_name": "delete"},
        )

    def _get_bulk_status_url(self, status=ProjectStatus.ACTIVE):
        return reverse(
            "projects:project_bulk_action",
            kwargs={"workspace_slug": self.workspace.slug, "action_name": f"status-{status}"},
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

    def test_create_view_presets_lead_when_single_member(self):
        """When only one workspace member exists, lead is preset to that member."""
        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertEqual(self.user.pk, form.initial["lead"])

    def test_create_view_presets_lead_from_latest_project(self):
        """When multiple members exist, lead is preset from the latest project."""
        other_user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user)
        ProjectFactory(workspace=self.workspace, lead=other_user)

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertEqual(other_user.pk, form.initial["lead"])

    def test_create_view_no_lead_preset_without_existing_project(self):
        """Without existing projects, lead is not preset (multi-member)."""
        other_user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user)

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertNotIn("lead", form.initial)

    def test_create_view_presets_lead_from_latest_not_oldest_project(self):
        """Lead preset comes from the most recently created project."""
        other_user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user)
        ProjectFactory(workspace=self.workspace, lead=self.user)
        ProjectFactory(workspace=self.workspace, lead=other_user)

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertEqual(other_user.pk, form.initial["lead"])

    def test_create_view_ignores_other_workspace_projects_for_lead(self):
        """Lead preset only considers projects from the current workspace."""
        other_user = UserFactory()
        other_workspace = WorkspaceFactory()
        MembershipFactory(workspace=self.workspace, user=other_user)
        ProjectFactory(workspace=other_workspace, lead=other_user)

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertNotIn("lead", form.initial)


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

    def test_delete_htmx_detail_page_returns_hx_location(self):
        """HTMX delete from detail page returns HX-Location with target."""
        project = ProjectFactory(workspace=self.workspace)
        project_pk = project.pk
        detail_url = self._get_detail_url(project)
        list_url = self._get_list_url()

        response = self.client.post(
            self._get_delete_url(project),
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL=f"http://testserver{detail_url}",
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("HX-Location", response)
        location_data = json.loads(response["HX-Location"])
        self.assertEqual(location_data["path"], list_url)
        self.assertEqual(location_data["target"], "#page-content")
        self.assertFalse(Project.objects.filter(pk=project_pk).exists())

    def test_delete_htmx_other_page_returns_hx_refresh(self):
        """HTMX delete from other page returns HX-Refresh."""
        project = ProjectFactory(workspace=self.workspace)
        project_pk = project.pk

        response = self.client.post(
            self._get_delete_url(project),
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver/w/workspace/projects/",
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(response["HX-Refresh"], "true")
        self.assertNotIn("HX-Location", response)
        self.assertFalse(Project.objects.filter(pk=project_pk).exists())


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

    def test_bulk_status_invalid_action_returns_404(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)
        invalid_url = reverse(
            "projects:project_bulk_action",
            kwargs={"workspace_slug": self.workspace.slug, "action_name": "status-invalid_status"},
        )

        response = self.client.post(invalid_url, {"projects": [project.key], "page": 1})

        self.assertEqual(404, response.status_code)
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
        return reverse(
            "projects:project_bulk_action",
            kwargs={"workspace_slug": self.workspace.slug, "action_name": "move"},
        )

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

    def test_bulk_move_dispatches_task(self):
        project = ProjectFactory(workspace=self.workspace)

        self.client.post(
            self._get_bulk_move_url(),
            {"projects": [project.key], "workspace": self.target_workspace.pk, "page": 1},
        )

        project.refresh_from_db()
        self.assertEqual(self.target_workspace, project.workspace)

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


class ProjectMoveViewTest(ProjectViewTestCase):
    """Tests for ProjectMoveView (single project move)."""

    def setUp(self):
        super().setUp()
        self.target_workspace = WorkspaceFactory()
        MembershipFactory(workspace=self.target_workspace, user=self.user, role=ROLE_MEMBER)
        self.project = ProjectFactory(workspace=self.workspace)

    def _get_move_url(self, project=None):
        project = project or self.project
        return reverse(
            "projects:project_move",
            kwargs={"workspace_slug": self.workspace.slug, "key": project.key},
        )

    def test_move_project_moves_project_to_target_workspace(self):
        response = self.client.post(self._get_move_url(), {"workspace": self.target_workspace.pk})
        self.project.refresh_from_db()
        self.assertEqual(self.target_workspace, self.project.workspace)
        self.assertRedirects(response, self._get_list_url())

    def test_move_project_moves_to_target_workspace(self):
        self.client.post(self._get_move_url(), {"workspace": self.target_workspace.pk})
        self.project.refresh_from_db()
        self.assertEqual(self.target_workspace, self.project.workspace)

    def test_move_to_workspace_without_membership_returns_404(self):
        other_workspace = WorkspaceFactory()  # user is NOT a member
        response = self.client.post(self._get_move_url(), {"workspace": other_workspace.pk})
        self.assertEqual(404, response.status_code)

    def test_move_nonexistent_project_returns_404(self):
        url = reverse(
            "projects:project_move",
            kwargs={"workspace_slug": self.workspace.slug, "key": "INVALID"},
        )
        response = self.client.post(url, {"workspace": self.target_workspace.pk})
        self.assertEqual(404, response.status_code)

    def test_get_not_allowed(self):
        response = self.client.get(self._get_move_url())
        self.assertEqual(405, response.status_code)


class MoveProgressViewTest(ProjectViewTestCase):
    """Tests for MoveProgressView (polling endpoint)."""

    def _get_progress_url(self, operation_id):
        return reverse(
            "projects:move_progress",
            kwargs={"workspace_slug": self.workspace.slug, "operation_id": operation_id},
        )

    def test_missing_operation_returns_hx_refresh(self):
        """When the operation is not in cache, the response triggers a client refresh."""
        response = self.client.get(self._get_progress_url("nonexistent"), headers={"HX-Request": "true"})
        self.assertEqual(response.get("HX-Refresh"), "true")

    def test_post_not_allowed(self):
        response = self.client.post(self._get_progress_url("test"))
        self.assertEqual(405, response.status_code)


class ProjectQuerySetWithProgressTest(TestCase):
    """Tests for ProjectQuerySet.with_progress()."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project)
        cls.story_done = StoryFactory(project=cls.project, parent=cls.epic, status=IssueStatus.DONE, estimated_points=3)
        cls.story_in_progress = StoryFactory(
            project=cls.project, parent=cls.epic, status=IssueStatus.IN_PROGRESS, estimated_points=5
        )
        cls.bug_todo = BugFactory(project=cls.project, parent=cls.epic, status=IssueStatus.DRAFT, estimated_points=2)
        cls.chore_todo = ChoreFactory(
            project=cls.project, parent=cls.epic, status=IssueStatus.READY, estimated_points=None
        )  # no points → weight 1

        # Second project — must not affect cls.project counts
        cls.other_project = ProjectFactory()
        other_epic = EpicFactory(project=cls.other_project)
        StoryFactory(project=cls.other_project, parent=other_epic, status=IssueStatus.DONE, estimated_points=10)

    def _get_project(self):
        return Project.objects.with_progress().get(pk=self.project.pk)

    def test_with_progress_adds_annotations(self):
        """with_progress adds the four progress annotations to projects."""
        p = self._get_project()
        self.assertTrue(hasattr(p, "total_done_points"))
        self.assertTrue(hasattr(p, "total_in_progress_points"))
        self.assertTrue(hasattr(p, "total_todo_points"))
        self.assertTrue(hasattr(p, "total_estimated_points"))

    def test_done_points(self):
        """total_done_points sums work items in done-category statuses."""
        p = self._get_project()
        self.assertEqual(3, p.total_done_points)

    def test_in_progress_points(self):
        """total_in_progress_points sums work items in in_progress-category statuses."""
        p = self._get_project()
        self.assertEqual(5, p.total_in_progress_points)

    def test_todo_points(self):
        """total_todo_points sums work items in todo-category statuses (None points → 1)."""
        p = self._get_project()
        # bug_todo=2, chore_todo=None→1
        self.assertEqual(3, p.total_todo_points)

    def test_total_estimated_points(self):
        """total_estimated_points is the sum of all three categories."""
        p = self._get_project()
        self.assertEqual(11, p.total_estimated_points)

    def test_other_project_not_affected(self):
        """Progress from another project does not bleed into this project."""
        other = Project.objects.with_progress().get(pk=self.other_project.pk)
        self.assertEqual(10, other.total_done_points)
        self.assertEqual(10, other.total_estimated_points)

    def test_empty_project_returns_zeros(self):
        """Project with no work items returns zero for all annotations."""
        empty = ProjectFactory()
        p = Project.objects.with_progress().get(pk=empty.pk)
        self.assertEqual(0, p.total_done_points)
        self.assertEqual(0, p.total_in_progress_points)
        self.assertEqual(0, p.total_todo_points)
        self.assertEqual(0, p.total_estimated_points)


class ProjectWithProgressMultipleMilestonesTest(TestCase):
    """Project progress: 2 milestones, 7 epics total, each with mixed work items."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()

        # Milestone 1 → 2 epics
        m1 = MilestoneFactory(project=cls.project)
        epic1 = EpicFactory(project=cls.project, parent=m1)
        epic2 = EpicFactory(project=cls.project, parent=m1)
        StoryFactory(project=cls.project, parent=epic1, status=IssueStatus.DONE, estimated_points=3)
        BugFactory(project=cls.project, parent=epic2, status=IssueStatus.IN_PROGRESS, estimated_points=5)

        # Milestone 2 → 5 epics
        m2 = MilestoneFactory(project=cls.project)
        epic3 = EpicFactory(project=cls.project, parent=m2)
        epic4 = EpicFactory(project=cls.project, parent=m2)
        epic5 = EpicFactory(project=cls.project, parent=m2)
        epic6 = EpicFactory(project=cls.project, parent=m2)
        epic7 = EpicFactory(project=cls.project, parent=m2)
        ChoreFactory(project=cls.project, parent=epic3, status=IssueStatus.DRAFT, estimated_points=2)
        StoryFactory(project=cls.project, parent=epic4, status=IssueStatus.DONE, estimated_points=7)
        ChoreFactory(project=cls.project, parent=epic5, status=IssueStatus.IN_PROGRESS, estimated_points=4)
        BugFactory(project=cls.project, parent=epic6, status=IssueStatus.READY, estimated_points=None)  # → weight 1
        StoryFactory(project=cls.project, parent=epic7, status=IssueStatus.DONE, estimated_points=6)

    def test_progress_across_all_milestones_and_epics(self):
        """Sums points across all 7 epics in both milestones. done=16, in_progress=9, todo=3, total=28."""
        p = Project.objects.with_progress().get(pk=self.project.pk)
        self.assertEqual(16, p.total_done_points)
        self.assertEqual(9, p.total_in_progress_points)
        self.assertEqual(3, p.total_todo_points)
        self.assertEqual(28, p.total_estimated_points)


class ProjectWithProgressOrphanWorkItemsTest(TestCase):
    """Project progress: root-level work items (no epic parent) count alongside epic children."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()

        # Epic with 3 children
        epic = EpicFactory(project=cls.project)
        StoryFactory(project=cls.project, parent=epic, status=IssueStatus.DONE, estimated_points=4)
        StoryFactory(project=cls.project, parent=epic, status=IssueStatus.IN_PROGRESS, estimated_points=2)
        BugFactory(project=cls.project, parent=epic, status=IssueStatus.DRAFT, estimated_points=1)

        # 3 orphan work items — no epic parent, root-level nodes
        StoryFactory(project=cls.project, status=IssueStatus.DONE, estimated_points=5)
        BugFactory(project=cls.project, status=IssueStatus.DRAFT, estimated_points=3)
        ChoreFactory(project=cls.project, status=IssueStatus.IN_PROGRESS, estimated_points=None)  # → weight 1

    def test_epic_children_and_orphans_all_counted(self):
        """
        Both epic children and root-level orphan work items contribute to progress.
        done=9, in_progress=3, todo=4, total=16.
        """
        p = Project.objects.with_progress().get(pk=self.project.pk)
        self.assertEqual(9, p.total_done_points)
        self.assertEqual(3, p.total_in_progress_points)
        self.assertEqual(4, p.total_todo_points)
        self.assertEqual(16, p.total_estimated_points)


class ProjectWithProgressEmptyHierarchyTest(TestCase):
    """Project progress: empty milestone + empty epics → all zeros."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        MilestoneFactory(project=cls.project)  # empty milestone — no epics linked
        EpicFactory(project=cls.project)  # empty epic, no milestone, no children
        EpicFactory(project=cls.project)  # empty epic, no milestone, no children

    def test_empty_hierarchy_returns_all_zeros(self):
        """Empty milestone and childless epics contribute no points to any category."""
        p = Project.objects.with_progress().get(pk=self.project.pk)
        self.assertEqual(0, p.total_done_points)
        self.assertEqual(0, p.total_in_progress_points)
        self.assertEqual(0, p.total_todo_points)
        self.assertEqual(0, p.total_estimated_points)
