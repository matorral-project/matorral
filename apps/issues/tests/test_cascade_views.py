"""Integration tests for cascade status change views."""

from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory, MilestoneFactory, StoryFactory, SubtaskFactory
from apps.issues.models import IssueStatus, SubtaskStatus
from apps.projects.factories import ProjectFactory
from apps.projects.models import ProjectStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class CascadeViewTestBase(TestCase):
    """Base test class for cascade view tests."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_issue_inline_edit_url(self, issue):
        return reverse(
            "issues:issue_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_epic_detail_inline_edit_url(self, epic):
        return reverse(
            "issues:epic_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": epic.key,
            },
        )

    def _get_project_inline_edit_url(self, project):
        return reverse(
            "projects:project_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def _get_cascade_apply_url(self):
        return reverse(
            "cascade_status_apply",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def _get_workspace_bulk_status_url(self):
        return reverse(
            "workspace_issues_bulk_status",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def _get_project_bulk_status_url(self):
        return reverse(
            "projects:projects_bulk_status",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )


class IssueInlineEditCascadeTest(CascadeViewTestBase):
    """Tests for cascade OOB content in issue row inline edit responses."""

    def test_status_change_with_eligible_children_returns_oob(self):
        """Changing epic status to DONE with draft children includes cascade OOB."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_issue_inline_edit_url(epic),
            {"title": epic.title, "status": IssueStatus.DONE},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
        self.assertIn("show-cascade-modal", response.get("HX-Trigger", ""))

    def test_status_change_without_eligible_children_no_oob(self):
        """Changing epic status when no children exist and siblings prevent cascade UP."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        # Add another non-completed orphan epic to prevent cascade UP to project
        EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_issue_inline_edit_url(epic),
            {"title": epic.title, "status": IssueStatus.DONE},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertNotIn("cascade-modal-content", content)

    def test_no_status_change_no_oob(self):
        """Updating title without changing status produces no cascade OOB."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_issue_inline_edit_url(epic),
            {"title": "Updated Title", "status": IssueStatus.DRAFT},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertNotIn("cascade-modal-content", content)


class EpicDetailInlineEditCascadeTest(CascadeViewTestBase):
    """Tests for cascade OOB in epic detail inline edit responses."""

    def test_epic_done_with_children_returns_cascade_oob(self):
        """Setting epic to DONE with draft stories includes cascade DOWN OOB."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_epic_detail_inline_edit_url(epic),
            {"title": epic.title, "status": IssueStatus.DONE},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
        self.assertIn("show-cascade-modal", response.get("HX-Trigger", ""))

    def test_epic_done_all_children_completed_offers_cascade_up(self):
        """Setting last epic to DONE under milestone offers cascade UP."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DONE)
        epic2 = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_epic_detail_inline_edit_url(epic2),
            {
                "title": epic2.title,
                "status": IssueStatus.DONE,
                "milestone": milestone.pk,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
        # Should include cascade UP to milestone
        self.assertIn(str(milestone.pk), content)


class ProjectInlineEditCascadeTest(CascadeViewTestBase):
    """Tests for cascade OOB in project inline edit responses."""

    def test_project_completed_with_active_milestones_returns_oob(self):
        """Completing project with non-completed milestones includes cascade OOB."""
        MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_project_inline_edit_url(self.project),
            {"name": self.project.name, "status": ProjectStatus.COMPLETED},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
        self.assertIn("show-cascade-modal", response.get("HX-Trigger", ""))

    def test_project_active_no_cascade(self):
        """Setting project to ACTIVE produces no cascade OOB."""
        response = self.client.post(
            self._get_project_inline_edit_url(self.project),
            {"name": self.project.name, "status": ProjectStatus.ACTIVE},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertNotIn("cascade-modal-content", content)


class CascadeApplyViewTest(CascadeViewTestBase):
    """Tests for the CascadeStatusApplyView endpoint."""

    def test_apply_cascade_down_updates_children(self):
        """POST with cascade_down=1 updates child statuses using multi-group format."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_down": "1",
                "down_group_count": "1",
                "down_ids_0": str(story.pk),
                "down_status_0": IssueStatus.DONE,
                "down_model_type_0": "issue",
            },
        )

        self.assertEqual(204, response.status_code)
        story.refresh_from_db()
        self.assertEqual(story.status, IssueStatus.DONE)

    def test_apply_cascade_up_updates_parent(self):
        """POST with cascade_up=1 updates parent status."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_up": "1",
                "up_id": str(milestone.pk),
                "up_status": IssueStatus.DONE,
                "up_model_type": "milestone",
            },
        )

        self.assertEqual(204, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.DONE)

    def test_apply_cascade_both_directions(self):
        """POST with both cascade_down=1 and cascade_up=1 updates both."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_down": "1",
                "down_group_count": "1",
                "down_ids_0": str(story.pk),
                "down_status_0": IssueStatus.DONE,
                "down_model_type_0": "issue",
                "cascade_up": "1",
                "up_id": str(milestone.pk),
                "up_status": IssueStatus.DONE,
                "up_model_type": "milestone",
            },
        )

        self.assertEqual(204, response.status_code)
        story.refresh_from_db()
        milestone.refresh_from_db()
        self.assertEqual(story.status, IssueStatus.DONE)
        self.assertEqual(milestone.status, IssueStatus.DONE)

    def test_apply_cascade_down_subtasks(self):
        """Cascade DOWN correctly updates subtasks."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_down": "1",
                "down_group_count": "1",
                "down_ids_0": str(subtask.pk),
                "down_status_0": SubtaskStatus.DONE,
                "down_model_type_0": "subtask",
            },
        )

        self.assertEqual(204, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(subtask.status, SubtaskStatus.DONE)

    def test_apply_cascade_up_project(self):
        """Cascade UP correctly updates project status."""
        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_up": "1",
                "up_id": str(self.project.pk),
                "up_status": ProjectStatus.COMPLETED,
                "up_model_type": "project",
            },
        )

        self.assertEqual(204, response.status_code)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.COMPLETED)

    def test_apply_cascade_down_multiple_groups(self):
        """POST with multiple groups updates all model types."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)
        epic = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DRAFT)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "cascade_down": "1",
                "down_group_count": "3",
                "down_ids_0": str(milestone.pk),
                "down_status_0": IssueStatus.DONE,
                "down_model_type_0": "milestone",
                "down_ids_1": f"{epic.pk},{story.pk}",
                "down_status_1": IssueStatus.DONE,
                "down_model_type_1": "issue",
                "down_ids_2": str(subtask.pk),
                "down_status_2": SubtaskStatus.DONE,
                "down_model_type_2": "subtask",
            },
        )

        self.assertEqual(204, response.status_code)
        milestone.refresh_from_db()
        epic.refresh_from_db()
        story.refresh_from_db()
        subtask.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.DONE)
        self.assertEqual(epic.status, IssueStatus.DONE)
        self.assertEqual(story.status, IssueStatus.DONE)
        self.assertEqual(subtask.status, SubtaskStatus.DONE)

    def test_no_cascade_flags_does_nothing(self):
        """POST without cascade_down or cascade_up flags makes no changes."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_cascade_apply_url(),
            {
                "up_id": str(milestone.pk),
                "up_status": IssueStatus.DONE,
                "up_model_type": "milestone",
            },
        )

        self.assertEqual(204, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.IN_PROGRESS)

    def test_cascade_apply_requires_login(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()

        response = self.client.post(self._get_cascade_apply_url(), {"cascade_down": "1"})

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)


class BulkStatusCascadeTest(CascadeViewTestBase):
    """Tests for cascade OOB content in bulk status change responses."""

    def test_workspace_bulk_status_with_cascade_returns_oob(self):
        """Workspace bulk status change with eligible children returns cascade OOB."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_workspace_bulk_status_url(),
            {
                "issues": [epic.key],
                "status": IssueStatus.DONE,
                "page": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
        self.assertIn("show-cascade-modal", response.get("HX-Trigger", ""))

    def test_workspace_bulk_status_no_cascade_when_no_children(self):
        """Workspace bulk status change without cascade-eligible items has no OOB."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        # Add another non-completed sibling to prevent cascade UP to project
        EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(
            self._get_workspace_bulk_status_url(),
            {
                "issues": [epic.key],
                "status": IssueStatus.DONE,
                "page": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        # Full page templates include cascade-modal-content in the shell template;
        # check HX-Trigger header which only appears when cascade is triggered
        self.assertNotIn("show-cascade-modal", response.get("HX-Trigger", ""))

    def test_project_bulk_status_with_cascade_returns_oob(self):
        """Project bulk status change with cascade-eligible children returns OOB."""
        project2 = ProjectFactory(workspace=self.workspace)
        MilestoneFactory(project=project2, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_project_bulk_status_url(),
            {
                "projects": [project2.key],
                "status": ProjectStatus.COMPLETED,
                "page": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        content = response.content.decode()
        self.assertIn("cascade-modal-content", content)
