from datetime import timedelta

from django.test import TestCase

from apps.issues.factories import BugFactory, ChoreFactory, StoryFactory
from apps.issues.models import Bug, Chore, IssueStatus, Story
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint, SprintStatus
from apps.workspaces.factories import WorkspaceFactory


class SprintStartTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def _make_sprint(self, **kwargs):
        return SprintFactory(workspace=self.workspace, **kwargs)

    def _fetch_with_committed_points(self, sprint):
        return Sprint.objects.for_workspace(self.workspace).with_committed_points().get(pk=sprint.pk)

    def test_start_planning_sprint(self):
        sprint = self._make_sprint(status=SprintStatus.PLANNING)
        sprint = self._fetch_with_committed_points(sprint)

        sprint.start()

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, SprintStatus.ACTIVE)
        # committed_points is set (0 since no issues assigned)
        self.assertEqual(sprint.committed_points, 0)

    def test_start_raises_when_not_planning(self):
        for status in [SprintStatus.COMPLETED, SprintStatus.ARCHIVED]:
            sprint = self._make_sprint(status=status)
            sprint = self._fetch_with_committed_points(sprint)

            with self.assertRaises(ValueError, msg=f"Expected ValueError for status={status}"):
                sprint.start()

    def test_start_raises_when_another_active(self):
        SprintFactory(workspace=self.workspace, active=True)

        planning_sprint = self._make_sprint(status=SprintStatus.PLANNING)
        planning_sprint = self._fetch_with_committed_points(planning_sprint)

        with self.assertRaises(ValueError):
            planning_sprint.start()


class SprintCompleteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def _make_active_sprint(self, **kwargs):
        sprint = SprintFactory(workspace=self.workspace, active=True, **kwargs)
        return Sprint.objects.for_workspace(self.workspace).with_completed_points().get(pk=sprint.pk)

    def _fetch_with_completed_points(self, sprint):
        return Sprint.objects.for_workspace(self.workspace).with_completed_points().get(pk=sprint.pk)

    def test_complete_active_sprint(self):
        sprint = self._make_active_sprint()

        sprint.complete()

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, SprintStatus.COMPLETED)
        self.assertEqual(sprint.completed_points, 0)

    def test_complete_raises_when_not_active(self):
        for status in [SprintStatus.PLANNING, SprintStatus.COMPLETED, SprintStatus.ARCHIVED]:
            sprint = SprintFactory(workspace=self.workspace, status=status)
            sprint = self._fetch_with_completed_points(sprint)

            with self.assertRaises(ValueError, msg=f"Expected ValueError for status={status}"):
                sprint.complete()

    def test_complete_rolls_over_incomplete_issues(self):
        sprint = self._make_active_sprint()
        next_sprint = SprintFactory(
            workspace=self.workspace,
            start_date=sprint.end_date + timedelta(days=1),
            end_date=sprint.end_date + timedelta(weeks=2, days=1),
        )
        StoryFactory(project=self.project, sprint=sprint, status=IssueStatus.IN_PROGRESS)
        BugFactory(project=self.project, sprint=sprint, status=IssueStatus.PLANNING)
        ChoreFactory(project=self.project, sprint=sprint, status=IssueStatus.READY)

        moved_count, returned_next = sprint.complete()

        self.assertEqual(moved_count, 3)
        self.assertEqual(returned_next.pk, next_sprint.pk)
        self.assertEqual(Story.objects.filter(sprint=next_sprint).count(), 1)
        self.assertEqual(Bug.objects.filter(sprint=next_sprint).count(), 1)
        self.assertEqual(Chore.objects.filter(sprint=next_sprint).count(), 1)

    def test_complete_returns_zero_when_no_next_sprint(self):
        sprint = self._make_active_sprint()
        StoryFactory(project=self.project, sprint=sprint, status=IssueStatus.IN_PROGRESS)

        moved_count, next_sprint = sprint.complete()

        self.assertEqual(moved_count, 0)
        self.assertIsNone(next_sprint)

    def test_complete_does_not_move_done_issues(self):
        sprint = self._make_active_sprint()
        next_sprint = SprintFactory(
            workspace=self.workspace,
            start_date=sprint.end_date + timedelta(days=1),
            end_date=sprint.end_date + timedelta(weeks=2, days=1),
        )
        StoryFactory(project=self.project, sprint=sprint, status=IssueStatus.DONE)

        moved_count, returned_next = sprint.complete()

        self.assertEqual(moved_count, 0)
        self.assertEqual(returned_next.pk, next_sprint.pk)
        self.assertEqual(Story.objects.filter(sprint=sprint).count(), 1)


class SprintArchiveTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def test_archive_completed_sprint(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)

        sprint.archive()

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, SprintStatus.ARCHIVED)

    def test_archive_planning_sprint(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        sprint.archive()

        sprint.refresh_from_db()
        self.assertEqual(sprint.status, SprintStatus.ARCHIVED)

    def test_archive_raises_when_active(self):
        sprint = SprintFactory(workspace=self.workspace, active=True)

        with self.assertRaises(ValueError):
            sprint.archive()
