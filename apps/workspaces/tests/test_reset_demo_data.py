from unittest.mock import patch

from django.test import TestCase

from apps.issues.models import Epic, Milestone, Story
from apps.projects.models import Project
from apps.sprints.models import Sprint
from apps.utils.tests.base import WorkspaceTestMixin
from apps.workspaces.demo_data import create_demo_project
from apps.workspaces.tasks import DEMO_USER_EMAIL, DEMO_USER_PASSWORD, reset_demo_workspace_data


class ResetDemoWorkspaceDataTest(WorkspaceTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin.email = DEMO_USER_EMAIL
        cls.admin.save(update_fields=["email"])
        create_demo_project(cls.workspace, cls.admin)

    def test_deletes_all_projects(self):
        self.assertGreater(Project.objects.filter(workspace=self.workspace).count(), 0)
        reset_demo_workspace_data()
        self.assertEqual(Project.objects.filter(workspace=self.workspace).count(), 0)

    def test_deletes_all_sprints(self):
        self.assertGreater(Sprint.objects.filter(workspace=self.workspace).count(), 0)
        reset_demo_workspace_data()
        self.assertEqual(Sprint.objects.filter(workspace=self.workspace).count(), 0)

    def test_cascades_milestones(self):
        project = Project.objects.filter(workspace=self.workspace).first()
        self.assertGreater(Milestone.objects.filter(project=project).count(), 0)
        reset_demo_workspace_data()
        self.assertEqual(Milestone.objects.filter(project=project).count(), 0)

    def test_cascades_epics(self):
        project = Project.objects.filter(workspace=self.workspace).first()
        self.assertGreater(Epic.objects.filter(project=project).count(), 0)
        reset_demo_workspace_data()
        self.assertEqual(Epic.objects.filter(project=project).count(), 0)

    def test_cascades_stories(self):
        project = Project.objects.filter(workspace=self.workspace).first()
        self.assertGreater(Story.objects.filter(project=project).count(), 0)
        reset_demo_workspace_data()
        self.assertEqual(Story.objects.filter(project=project).count(), 0)

    def test_resets_password(self):
        self.admin.set_password("changed-by-visitor")
        self.admin.save(update_fields=["password"])
        self.assertFalse(self.admin.check_password(DEMO_USER_PASSWORD))

        reset_demo_workspace_data()

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(DEMO_USER_PASSWORD))


class ResetDemoWorkspaceDataNoUserTest(TestCase):
    @patch("apps.workspaces.tasks.logger")
    def test_warns_when_demo_user_not_found(self, mock_logger):
        reset_demo_workspace_data()
        mock_logger.warning.assert_called_once_with(
            "Demo user '%s' not found, skipping workspace reset",
            DEMO_USER_EMAIL,
        )
