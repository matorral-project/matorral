from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.issues.factories import BugFactory, ChoreFactory, StoryFactory
from apps.issues.models import IssueStatus
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint, SprintStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import WorkspaceFactory


class WithCommittedPointsTest(TestCase):
    """Tests for SprintQuerySet.with_committed_points()."""

    @classmethod
    def setUpTestData(cls):
        cls.sprint = SprintFactory()
        cls.project = ProjectFactory(workspace=cls.sprint.workspace)

    def test_no_items_returns_zero(self):
        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_committed_points().get()
        self.assertEqual(sprint.computed_committed_points, 0)

    def test_sums_estimated_points_across_types(self):
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5)
        BugFactory(project=self.project, sprint=self.sprint, estimated_points=3)
        ChoreFactory(project=self.project, sprint=self.sprint, estimated_points=2)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_committed_points().get()
        self.assertEqual(sprint.computed_committed_points, 10)

    def test_ignores_null_estimated_points(self):
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5)
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=None)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_committed_points().get()
        self.assertEqual(sprint.computed_committed_points, 5)

    def test_ignores_items_in_other_sprints(self):
        other_sprint = SprintFactory(workspace=self.sprint.workspace)
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5)
        StoryFactory(project=self.project, sprint=other_sprint, estimated_points=10)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_committed_points().get()
        self.assertEqual(sprint.computed_committed_points, 5)


class WithCompletedPointsTest(TestCase):
    """Tests for SprintQuerySet.with_completed_points()."""

    @classmethod
    def setUpTestData(cls):
        cls.sprint = SprintFactory()
        cls.project = ProjectFactory(workspace=cls.sprint.workspace)

    def test_no_items_returns_zero(self):
        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_completed_points().get()
        self.assertEqual(sprint.computed_completed_points, 0)

    def test_sums_only_done_items(self):
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5, status=IssueStatus.DONE)
        BugFactory(project=self.project, sprint=self.sprint, estimated_points=3, status=IssueStatus.WONT_DO)
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=8, status=IssueStatus.IN_PROGRESS)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_completed_points().get()
        self.assertEqual(sprint.computed_completed_points, 8)

    def test_ignores_non_done_items(self):
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5, status=IssueStatus.DRAFT)
        BugFactory(project=self.project, sprint=self.sprint, estimated_points=3, status=IssueStatus.IN_PROGRESS)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_completed_points().get()
        self.assertEqual(sprint.computed_completed_points, 0)


class WithVelocityTest(TestCase):
    """Tests for SprintQuerySet.with_velocity()."""

    @classmethod
    def setUpTestData(cls):
        cls.sprint = SprintFactory()
        cls.project = ProjectFactory(workspace=cls.sprint.workspace)

    def test_annotates_both_committed_and_completed(self):
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=5, status=IssueStatus.DONE)
        StoryFactory(project=self.project, sprint=self.sprint, estimated_points=3, status=IssueStatus.IN_PROGRESS)

        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_velocity().get()
        self.assertEqual(sprint.computed_committed_points, 8)
        self.assertEqual(sprint.computed_completed_points, 5)

    def test_empty_sprint(self):
        sprint = Sprint.objects.filter(pk=self.sprint.pk).with_velocity().get()
        self.assertEqual(sprint.computed_committed_points, 0)
        self.assertEqual(sprint.computed_completed_points, 0)


class AvailableTest(TestCase):
    """Tests for SprintQuerySet.available()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def _keys(self, qs):
        return list(qs.values_list("key", flat=True))

    def test_excludes_completed_and_archived(self):
        planning = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)

        result = Sprint.objects.for_workspace(self.workspace).available()
        self.assertEqual(self._keys(result), [planning.key])

    def test_active_sprint_comes_before_planning(self):
        planning = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        active = SprintFactory(workspace=self.workspace, active=True)

        keys = self._keys(Sprint.objects.for_workspace(self.workspace).available())
        self.assertEqual(keys, [active.key, planning.key])

    def test_multiple_planning_sprints_ordered_by_start_date_desc(self):
        today = timezone.now().date()
        older = SprintFactory(
            workspace=self.workspace, status=SprintStatus.PLANNING, start_date=today - timedelta(weeks=2)
        )
        newer = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING, start_date=today)

        keys = self._keys(Sprint.objects.for_workspace(self.workspace).available())
        self.assertEqual(keys, [newer.key, older.key])

    def test_empty_when_no_available_sprints(self):
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)

        result = Sprint.objects.for_workspace(self.workspace).available()
        self.assertFalse(result.exists())


class GetCreationDefaultsTest(TestCase):
    """Tests for SprintManager.get_creation_defaults()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def _defaults(self, workspace_members=None):
        return Sprint.objects.get_creation_defaults(self.workspace, workspace_members)

    def test_returns_empty_dict_when_no_sprints(self):
        result = self._defaults()
        self.assertEqual(result, {})

    def test_ignores_archived_sprints(self):
        SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)
        result = self._defaults()
        self.assertEqual(result, {})

    def test_uses_duration_of_last_sprint_by_start_date(self):
        today = timezone.now().date()
        # 3-week sprint
        sprint = SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=3),
            end_date=today,
        )
        duration = sprint.end_date - sprint.start_date

        result = self._defaults()

        expected_start = sprint.end_date + timedelta(days=1)
        self.assertEqual(result["start_date"], expected_start)
        self.assertEqual(result["end_date"], expected_start + duration)

    def test_picks_latest_sprint_by_start_date(self):
        today = timezone.now().date()
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=6),
            end_date=today - timedelta(weeks=4),
        )
        # 1-week sprint, more recent
        latest = SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=2),
            end_date=today - timedelta(weeks=1),
        )
        duration = latest.end_date - latest.start_date

        result = self._defaults()

        expected_start = latest.end_date + timedelta(days=1)
        self.assertEqual(result["start_date"], expected_start)
        self.assertEqual(result["end_date"], expected_start + duration)

    def test_includes_planning_and_active_sprints(self):
        today = timezone.now().date()
        sprint = SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.PLANNING,
            start_date=today,
            end_date=today + timedelta(weeks=2),
        )
        duration = sprint.end_date - sprint.start_date

        result = self._defaults()

        expected_start = sprint.end_date + timedelta(days=1)
        self.assertEqual(result["start_date"], expected_start)
        self.assertEqual(result["end_date"], expected_start + duration)

    def test_prefills_capacity_from_latest_sprint(self):
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED, capacity=40)
        result = self._defaults()
        self.assertEqual(result["capacity"], 40)

    def test_skips_capacity_when_none(self):
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED, capacity=None)
        result = self._defaults()
        self.assertNotIn("capacity", result)

    def test_prefills_owner_from_latest_sprint(self):
        user = UserFactory()
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED, owner=user)

        result = self._defaults()

        self.assertEqual(result["owner"], user.pk)

    def test_single_workspace_member_overrides_sprint_owner(self):
        sprint_owner = UserFactory()
        single_member = UserFactory()
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED, owner=sprint_owner)

        result = self._defaults(workspace_members=[single_member])

        self.assertEqual(result["owner"], single_member.pk)

    def test_multiple_workspace_members_uses_sprint_owner(self):
        sprint_owner = UserFactory()
        SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED, owner=sprint_owner)
        members = [UserFactory(), UserFactory()]

        result = self._defaults(workspace_members=members)

        self.assertEqual(result["owner"], sprint_owner.pk)


class NeedingNextSprintTest(TestCase):
    """Tests for SprintQuerySet.needing_next_sprint()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def test_returns_active_sprint_without_planning(self):
        """An active sprint with no planning sprint after it should be returned."""
        active = SprintFactory(workspace=self.workspace, active=True)

        result = Sprint.objects.needing_next_sprint()

        self.assertQuerySetEqual(result, [active])

    def test_excludes_when_planning_exists_after(self):
        """An active sprint with a planning sprint after it should be excluded."""
        today = timezone.now().date()
        SprintFactory(workspace=self.workspace, active=True)
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.PLANNING,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(weeks=2),
        )

        result = Sprint.objects.needing_next_sprint()

        self.assertFalse(result.exists())

    def test_excludes_when_later_active_exists(self):
        """Only the latest active/completed sprint per workspace qualifies."""
        today = timezone.now().date()
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=4),
            end_date=today - timedelta(weeks=2),
        )
        latest = SprintFactory(workspace=self.workspace, active=True)

        result = Sprint.objects.needing_next_sprint()

        self.assertQuerySetEqual(result, [latest])

    def test_multiple_workspaces_returns_one_per_workspace(self):
        """Each workspace's latest qualifying sprint is returned independently."""
        today = timezone.now().date()
        other_workspace = WorkspaceFactory()

        sprint_a = SprintFactory(workspace=self.workspace, active=True)
        sprint_b = SprintFactory(
            workspace=other_workspace,
            status=SprintStatus.COMPLETED,
            start_date=today - timedelta(weeks=2),
            end_date=today,
        )

        result = Sprint.objects.needing_next_sprint()

        self.assertEqual(set(result), {sprint_a, sprint_b})
