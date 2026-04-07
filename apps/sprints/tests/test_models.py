from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint, SprintStatus
from apps.workspaces.factories import WorkspaceFactory


class SprintStartTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def _make_sprint(self, **kwargs):
        return SprintFactory(workspace=self.workspace, **kwargs)

    def _fetch_with_annotation(self, sprint):
        return Sprint.objects.for_workspace(self.workspace).with_committed_points().get(pk=sprint.pk)

    def test_start_planning_sprint(self):
        sprint = self._make_sprint(status=SprintStatus.PLANNING)
        sprint = self._fetch_with_annotation(sprint)

        sprint.start()

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, SprintStatus.ACTIVE)
        # committed_points is set (0 since no issues assigned)
        self.assertEqual(sprint.committed_points, 0)

    def test_start_raises_when_not_planning(self):
        for status in [SprintStatus.COMPLETED, SprintStatus.ARCHIVED]:
            sprint = self._make_sprint(status=status)
            sprint = self._fetch_with_annotation(sprint)

            with self.assertRaises(ValueError, msg=f"Expected ValueError for status={status}"):
                sprint.start()

    def test_start_raises_when_another_active(self):
        # Create an already-active sprint in the same workspace
        today = timezone.now().date()
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.ACTIVE,
            start_date=today - timedelta(weeks=2),
            end_date=today,
        )

        planning_sprint = self._make_sprint(status=SprintStatus.PLANNING)
        planning_sprint = self._fetch_with_annotation(planning_sprint)

        with self.assertRaises(ValueError):
            planning_sprint.start()
