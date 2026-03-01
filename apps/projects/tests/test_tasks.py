from django.test import TestCase

from apps.projects.factories import ProjectFactory
from apps.projects.tasks import move_project_task
from apps.workspaces.factories import WorkspaceFactory


class MoveProjectTaskTest(TestCase):
    """Tests for the move_project_task Celery task."""

    @classmethod
    def setUpTestData(cls):
        cls.source_workspace = WorkspaceFactory()
        cls.target_workspace = WorkspaceFactory()

    def test_move_project_task_happy_path(self):
        """Task moves the project to the target workspace."""
        project = ProjectFactory(workspace=self.source_workspace)

        move_project_task(project.pk, self.target_workspace.pk)

        project.refresh_from_db()
        self.assertEqual(project.workspace, self.target_workspace)
