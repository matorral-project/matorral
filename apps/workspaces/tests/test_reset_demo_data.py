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

    def test_recreates_projects_with_new_ids(self):
        old_ids = set(Project.objects.filter(workspace=self.workspace).values_list("id", flat=True))
        self.assertGreater(len(old_ids), 0)
        reset_demo_workspace_data()
        new_ids = set(Project.objects.filter(workspace=self.workspace).values_list("id", flat=True))
        self.assertGreater(len(new_ids), 0)
        self.assertTrue(old_ids.isdisjoint(new_ids), "Projects should be recreated with new IDs after reset")

    def test_recreates_sprints_with_new_ids(self):
        old_ids = set(Sprint.objects.filter(workspace=self.workspace).values_list("id", flat=True))
        self.assertGreater(len(old_ids), 0)
        reset_demo_workspace_data()
        new_ids = set(Sprint.objects.filter(workspace=self.workspace).values_list("id", flat=True))
        self.assertGreater(len(new_ids), 0)
        self.assertTrue(old_ids.isdisjoint(new_ids), "Sprints should be recreated with new IDs after reset")

    def test_recreates_milestones_with_new_ids(self):
        old_project = Project.objects.filter(workspace=self.workspace).first()
        old_ids = set(Milestone.objects.filter(project=old_project).values_list("id", flat=True))
        self.assertGreater(len(old_ids), 0)
        reset_demo_workspace_data()
        new_project = Project.objects.filter(workspace=self.workspace).first()
        new_ids = set(Milestone.objects.filter(project=new_project).values_list("id", flat=True))
        self.assertGreater(len(new_ids), 0)
        self.assertTrue(old_ids.isdisjoint(new_ids), "Milestones should be recreated with new IDs after reset")

    def test_recreates_epics_with_new_ids(self):
        old_project = Project.objects.filter(workspace=self.workspace).first()
        old_ids = set(Epic.objects.filter(project=old_project).values_list("id", flat=True))
        self.assertGreater(len(old_ids), 0)
        reset_demo_workspace_data()
        new_project = Project.objects.filter(workspace=self.workspace).first()
        new_ids = set(Epic.objects.filter(project=new_project).values_list("id", flat=True))
        self.assertGreater(len(new_ids), 0)
        self.assertTrue(old_ids.isdisjoint(new_ids), "Epics should be recreated with new IDs after reset")

    def test_recreates_stories_with_new_ids(self):
        old_project = Project.objects.filter(workspace=self.workspace).first()
        old_ids = set(Story.objects.filter(project=old_project).values_list("id", flat=True))
        self.assertGreater(len(old_ids), 0)
        reset_demo_workspace_data()
        new_project = Project.objects.filter(workspace=self.workspace).first()
        new_ids = set(Story.objects.filter(project=new_project).values_list("id", flat=True))
        self.assertGreater(len(new_ids), 0)
        self.assertTrue(old_ids.isdisjoint(new_ids), "Stories should be recreated with new IDs after reset")

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
