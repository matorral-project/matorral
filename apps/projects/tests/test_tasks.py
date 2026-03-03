from django.test import TestCase

from apps.projects.factories import ProjectFactory
from apps.projects.tasks import move_projects_task, start_move_operation
from apps.workspaces.factories import WorkspaceFactory


class MoveProjectsTaskTest(TestCase):
    """Tests for the move_projects_task Celery task."""

    @classmethod
    def setUpTestData(cls):
        cls.source_workspace = WorkspaceFactory()
        cls.target_workspace = WorkspaceFactory()

    def test_move_single_project(self):
        """Task moves a single project to the target workspace."""
        project = ProjectFactory(workspace=self.source_workspace)

        move_projects_task(project_ids=[project.pk], target_workspace_id=self.target_workspace.pk)

        project.refresh_from_db()
        self.assertEqual(project.workspace, self.target_workspace)

    def test_move_multiple_projects(self):
        """Task moves multiple projects to the target workspace."""
        project1 = ProjectFactory(workspace=self.source_workspace)
        project2 = ProjectFactory(workspace=self.source_workspace)

        move_projects_task(
            project_ids=[project1.pk, project2.pk],
            target_workspace_id=self.target_workspace.pk,
        )

        project1.refresh_from_db()
        project2.refresh_from_db()
        self.assertEqual(project1.workspace, self.target_workspace)
        self.assertEqual(project2.workspace, self.target_workspace)


class StartMoveOperationTest(TestCase):
    """Tests for start_move_operation helper."""

    @classmethod
    def setUpTestData(cls):
        cls.source_workspace = WorkspaceFactory()
        cls.target_workspace = WorkspaceFactory()

    def test_returns_operation_id(self):
        project = ProjectFactory(workspace=self.source_workspace)
        operation_id = start_move_operation([project.pk], self.target_workspace.pk)
        self.assertIsInstance(operation_id, str)
        self.assertGreater(len(operation_id), 0)

    def test_moves_project(self):
        """start_move_operation dispatches the task which moves the project (eager mode)."""
        project = ProjectFactory(workspace=self.source_workspace)
        start_move_operation([project.pk], self.target_workspace.pk)
        project.refresh_from_db()
        self.assertEqual(project.workspace, self.target_workspace)
