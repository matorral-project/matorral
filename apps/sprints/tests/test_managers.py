from django.test import TestCase

from apps.issues.factories import BugFactory, ChoreFactory, StoryFactory
from apps.issues.models import IssueStatus
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint


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
