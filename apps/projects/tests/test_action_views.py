import json

from django.urls import reverse

from apps.issues.factories import EpicFactory, MilestoneFactory, StoryFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project, ProjectStatus
from apps.projects.tests.test_views import ProjectViewTestCase
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_MEMBER


class ProjectActionUrlMixin:
    """URL helpers for the generic project action dispatch endpoints."""

    def _get_action_url(self, project, action_name):
        return reverse(
            "projects:project_action",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
                "action_name": action_name,
            },
        )

    def _get_action_confirm_url(self, project, action_name):
        return reverse(
            "projects:project_action_confirm",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
                "action_name": action_name,
            },
        )


class ProjectActionConfirmViewTest(ProjectActionUrlMixin, ProjectViewTestCase):
    """Tests for ProjectActionConfirmView (GET confirm modal)."""

    def test_confirm_returns_modal_html(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.get(self._get_action_confirm_url(project, "start"))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Start Project?")

    def test_delete_confirm_shows_child_counts(self):
        project = ProjectFactory(workspace=self.workspace)
        MilestoneFactory(project=project)
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic)

        response = self.client.get(self._get_action_confirm_url(project, "delete"))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "1 milestone")
        self.assertContains(response, "1 epic")
        self.assertContains(response, "1 work item")

    def test_move_confirm_lists_target_workspaces(self):
        project = ProjectFactory(workspace=self.workspace)
        target = WorkspaceFactory(name="Other Workspace")
        MembershipFactory(workspace=target, user=self.user, role=ROLE_MEMBER)

        response = self.client.get(self._get_action_confirm_url(project, "move"))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Other Workspace")
        self.assertContains(response, "Target workspace")

    def test_unknown_action_returns_404(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.get(self._get_action_confirm_url(project, "nope"))

        self.assertEqual(404, response.status_code)

    def test_unavailable_action_returns_404(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.ACTIVE)

        response = self.client.get(self._get_action_confirm_url(project, "start"))

        self.assertEqual(404, response.status_code)

    def test_post_not_allowed(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(self._get_action_confirm_url(project, "delete"))

        self.assertEqual(405, response.status_code)


class ProjectActionViewTest(ProjectActionUrlMixin, ProjectViewTestCase):
    """Tests for ProjectActionView (POST execute)."""

    def test_start_transitions_draft_to_active(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(self._get_action_url(project, "start"))

        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project.status)
        self.assertRedirects(response, project.get_absolute_url())

    def test_complete_transitions_active_to_completed(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.ACTIVE)

        self.client.post(self._get_action_url(project, "complete"))

        project.refresh_from_db()
        self.assertEqual(ProjectStatus.COMPLETED, project.status)

    def test_reopen_transitions_completed_to_active(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.COMPLETED)

        self.client.post(self._get_action_url(project, "reopen"))

        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project.status)

    def test_archive_transitions_to_archived(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.ACTIVE)

        self.client.post(self._get_action_url(project, "archive"))

        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ARCHIVED, project.status)

    def test_clone_creates_copy_and_redirects(self):
        project = ProjectFactory(workspace=self.workspace, name="Original")

        response = self.client.post(self._get_action_url(project, "clone"))

        cloned = Project.objects.get(name="Original (Copy)")
        self.assertEqual(self.user, cloned.created_by)
        self.assertRedirects(response, cloned.get_absolute_url())

    def test_move_moves_project_to_target_workspace(self):
        target = WorkspaceFactory()
        MembershipFactory(workspace=target, user=self.user, role=ROLE_MEMBER)
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(self._get_action_url(project, "move"), {"workspace": target.pk})

        project.refresh_from_db()
        self.assertEqual(target, project.workspace)
        self.assertRedirects(response, self._get_list_url())

    def test_move_to_unauthorized_workspace_returns_404(self):
        project = ProjectFactory(workspace=self.workspace)
        unrelated = WorkspaceFactory()

        response = self.client.post(self._get_action_url(project, "move"), {"workspace": unrelated.pk})

        self.assertEqual(404, response.status_code)
        project.refresh_from_db()
        self.assertEqual(self.workspace, project.workspace)

    def test_delete_removes_project_and_redirects_to_list(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(self._get_action_url(project, "delete"))

        self.assertFalse(Project.objects.filter(pk=project.pk).exists())
        self.assertRedirects(response, self._get_list_url())

    def test_delete_via_htmx_from_detail_page_returns_hx_location(self):
        """HTMX delete from the project's own detail page returns HX-Location with target."""
        project = ProjectFactory(workspace=self.workspace)
        detail_url = self._get_detail_url(project)

        response = self.client.post(
            self._get_action_url(project, "delete"),
            headers={"hx-request": "true", "hx-current-url": f"http://testserver{detail_url}"},
        )

        self.assertEqual(200, response.status_code)
        location_data = json.loads(response["HX-Location"])
        self.assertEqual(self._get_list_url(), location_data["path"])
        self.assertEqual("#page-content", location_data["target"])
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_delete_via_htmx_returns_client_refresh(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_action_url(project, "delete"),
            headers={"hx-request": "true"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("true", response.headers.get("HX-Refresh"))
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_clone_via_htmx_returns_hx_redirect(self):
        project = ProjectFactory(workspace=self.workspace, name="Original")

        response = self.client.post(
            self._get_action_url(project, "clone"),
            headers={"hx-request": "true"},
        )

        cloned = Project.objects.get(name="Original (Copy)")
        self.assertEqual(200, response.status_code)
        self.assertEqual(cloned.get_absolute_url(), response.headers["HX-Redirect"])

    def test_start_via_htmx_returns_hx_redirect(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.post(
            self._get_action_url(project, "start"),
            headers={"hx-request": "true"},
        )

        project.refresh_from_db()
        self.assertEqual(ProjectStatus.ACTIVE, project.status)
        self.assertEqual(200, response.status_code)
        self.assertEqual(project.get_absolute_url(), response.headers["HX-Redirect"])

    def test_unknown_action_returns_404(self):
        project = ProjectFactory(workspace=self.workspace)

        response = self.client.post(self._get_action_url(project, "nope"))

        self.assertEqual(404, response.status_code)

    def test_unavailable_action_returns_404(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.ARCHIVED)

        response = self.client.post(self._get_action_url(project, "start"))

        self.assertEqual(404, response.status_code)

    def test_get_not_allowed(self):
        project = ProjectFactory(workspace=self.workspace, status=ProjectStatus.DRAFT)

        response = self.client.get(self._get_action_url(project, "start"))

        self.assertEqual(405, response.status_code)

    def test_project_from_other_workspace_returns_404(self):
        other_workspace = WorkspaceFactory()
        project = ProjectFactory(workspace=other_workspace)

        response = self.client.post(self._get_action_url(project, "archive"))

        self.assertEqual(404, response.status_code)
