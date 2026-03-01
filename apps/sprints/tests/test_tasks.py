from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.tasks import create_next_sprints
from apps.workspaces.factories import WorkspaceFactory


class CreateNextSprintsTest(TestCase):
    """Tests for the create_next_sprints Celery task."""

    def test_creates_next_sprint_for_active_sprint(self):
        """Task creates a planning sprint after an active sprint."""
        workspace = WorkspaceFactory()
        start_date = timezone.now().date()
        end_date = start_date + timedelta(weeks=2)
        capacity = 20

        active_sprint = SprintFactory(
            workspace=workspace,
            status=SprintStatus.ACTIVE,
            start_date=start_date,
            end_date=end_date,
            capacity=capacity,
        )

        create_next_sprints()

        planning_sprints = Sprint.objects.for_workspace(workspace).filter(status=SprintStatus.PLANNING)
        self.assertEqual(1, planning_sprints.count())

        new_sprint = planning_sprints.first()
        duration = active_sprint.end_date - active_sprint.start_date

        self.assertEqual(active_sprint.end_date + timedelta(days=1), new_sprint.start_date)
        self.assertEqual(active_sprint.end_date + timedelta(days=1) + duration, new_sprint.end_date)
        self.assertEqual(capacity, new_sprint.capacity)

    def test_creates_next_sprint_for_completed_sprint(self):
        """Task creates a planning sprint after a completed sprint."""
        workspace = WorkspaceFactory()
        start_date = timezone.now().date() - timedelta(weeks=3)
        end_date = start_date + timedelta(weeks=2)
        capacity = 15

        SprintFactory(
            workspace=workspace,
            status=SprintStatus.COMPLETED,
            start_date=start_date,
            end_date=end_date,
            capacity=capacity,
        )

        create_next_sprints()

        new_sprint = Sprint.objects.for_workspace(workspace).filter(status=SprintStatus.PLANNING).first()

        self.assertIsNotNone(new_sprint)
        self.assertEqual(end_date + timedelta(days=1), new_sprint.start_date)
        self.assertEqual(capacity, new_sprint.capacity)

    def test_does_not_duplicate_existing_planning_sprint(self):
        """Task does not create a duplicate planning sprint for next period."""
        workspace = WorkspaceFactory()
        start_date = timezone.now().date()
        end_date = start_date + timedelta(weeks=2)

        active_sprint = SprintFactory(
            workspace=workspace,
            status=SprintStatus.ACTIVE,
            start_date=start_date,
            end_date=end_date,
        )

        duration = active_sprint.end_date - active_sprint.start_date
        existing_planning = SprintFactory(
            workspace=workspace,
            status=SprintStatus.PLANNING,
            start_date=active_sprint.end_date + timedelta(days=1),
            end_date=active_sprint.end_date + timedelta(days=1) + duration,
        )

        create_next_sprints()

        planning_sprints = Sprint.objects.for_workspace(workspace).filter(status=SprintStatus.PLANNING)
        self.assertEqual(1, planning_sprints.count())
        self.assertEqual(existing_planning.pk, planning_sprints.first().pk)

    def test_workspace_with_no_sprints_creates_nothing(self):
        """Task creates nothing and raises no exception for workspace with no sprints."""
        workspace = WorkspaceFactory()

        create_next_sprints()

        self.assertEqual(0, Sprint.objects.for_workspace(workspace).count())

    def test_multiple_workspaces_handled_separately(self):
        """Task handles multiple workspaces independently."""
        workspace1 = WorkspaceFactory()
        workspace2 = WorkspaceFactory()
        start_date = timezone.now().date()

        SprintFactory(
            workspace=workspace1,
            status=SprintStatus.ACTIVE,
            start_date=start_date,
            end_date=start_date + timedelta(weeks=2),
        )

        create_next_sprints()

        self.assertEqual(1, Sprint.objects.for_workspace(workspace1).planning().count())
        self.assertEqual(0, Sprint.objects.for_workspace(workspace2).count())

    def test_uses_latest_sprint_when_multiple_exist(self):
        """Task uses the latest sprint (by end_date) when multiple exist."""
        workspace = WorkspaceFactory()
        today = timezone.now().date()

        SprintFactory(
            workspace=workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=6),
            end_date=today - timedelta(weeks=4),
            capacity=10,
        )

        latest = SprintFactory(
            workspace=workspace,
            status=SprintStatus.ACTIVE,
            start_date=today - timedelta(weeks=2),
            end_date=today,
            capacity=25,
        )

        create_next_sprints()

        new_sprint = Sprint.objects.for_workspace(workspace).planning().first()
        self.assertIsNotNone(new_sprint)
        self.assertEqual(latest.end_date + timedelta(days=1), new_sprint.start_date)
        self.assertEqual(25, new_sprint.capacity)
