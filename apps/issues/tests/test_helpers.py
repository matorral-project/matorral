from django.test import TestCase

from apps.issues.factories import BugFactory, EpicFactory, MilestoneFactory, StoryFactory
from apps.issues.helpers import build_grouped_issues, calculate_progress
from apps.issues.models import BaseIssue, Epic, IssuePriority, IssueStatus
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.users.factories import CustomUserFactory


class BuildGroupedIssuesQueryCountTest(TestCase):
    """Tests for query counts in build_grouped_issues().

    These tests document and verify query behavior to detect N+1 issues.
    """

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.user1 = CustomUserFactory(first_name="Alice", last_name="Smith")
        cls.user2 = CustomUserFactory(first_name="Bob", last_name="Jones")

        # Create 2 epics with 5 stories each (10 issues under epics)
        cls.epic1 = EpicFactory(project=cls.project, title="Epic 1")
        cls.epic2 = EpicFactory(project=cls.project, title="Epic 2")

        for i in range(5):
            assignee = cls.user1 if i % 2 == 0 else cls.user2
            StoryFactory(project=cls.project, parent=cls.epic1, assignee=assignee)
            StoryFactory(project=cls.project, parent=cls.epic2, assignee=assignee)

    def _get_issues_queryset(self):
        """Return a queryset with select_related as used in views."""
        return BaseIssue.objects.for_project(self.project).select_related("project", "assignee")

    def test_group_by_status_query_count(self):
        """Grouping by status should not cause additional queries."""
        issues = list(self._get_issues_queryset())

        with self.assertNumQueries(0):
            result = build_grouped_issues(issues, "status")

        self.assertTrue(len(result) > 0)

    def test_group_by_priority_query_count(self):
        """Grouping by priority should not cause additional queries."""
        issues = list(self._get_issues_queryset())

        with self.assertNumQueries(0):
            result = build_grouped_issues(issues, "priority")

        self.assertTrue(len(result) > 0)

    def test_group_by_assignee_query_count(self):
        """Grouping by assignee should not cause additional queries.

        The assignee is prefetched via select_related, so get_display_name()
        should not trigger extra queries.
        """
        issues = list(self._get_issues_queryset())

        with self.assertNumQueries(0):
            result = build_grouped_issues(issues, "assignee")

        self.assertTrue(len(result) > 0)

    def test_group_by_epic_query_count(self):
        """Grouping by epic should only cause 1 query to prefetch parent epics."""
        # Only get non-epic issues (stories) that have a parent
        issues = list(self._get_issues_queryset().filter(depth__gt=1))

        # Should be 1 query to fetch all parent epics, regardless of issue count
        with self.assertNumQueries(1):
            result = build_grouped_issues(issues, "epic")

        self.assertTrue(len(result) > 0)
        # Verify we have grouped issues under their epics
        group_names = [group["name"] for group in result]
        self.assertIn(f"[{self.epic1.key}] {self.epic1.title}", group_names)
        self.assertIn(f"[{self.epic2.key}] {self.epic2.title}", group_names)
        # Verify epic_key is included in the results
        epic_keys = [group.get("epic_key") for group in result]
        self.assertIn(self.epic1.key, epic_keys)
        self.assertIn(self.epic2.key, epic_keys)
        # Verify epic object is included and status/priority can be accessed without queries
        with self.assertNumQueries(0):
            for group in result:
                if group.get("epic"):
                    _ = group["epic"].status
                    _ = group["epic"].priority
                    _ = group["epic"].get_status_display()
                    _ = group["epic"].get_priority_display()

    def test_group_by_epic_includes_empty_epics_when_project_provided(self):
        """When project is provided, epics without children should be included."""
        # Create an epic with no children
        empty_epic = EpicFactory(project=self.project, title="Empty Epic")

        # Get only non-epic issues (won't include the empty epic's children since there are none)
        issues = list(self._get_issues_queryset().filter(depth__gt=1))

        # Without project, the empty epic should not appear
        result_without_project = build_grouped_issues(issues, "epic")
        group_names = [group["name"] for group in result_without_project]
        self.assertNotIn(f"[{empty_epic.key}] {empty_epic.title}", group_names)

        # With project, the empty epic should appear (with 0 issues)
        result_with_project = build_grouped_issues(issues, "epic", project=self.project)
        group_names = [group["name"] for group in result_with_project]
        self.assertIn(f"[{empty_epic.key}] {empty_epic.title}", group_names)

        # Verify the empty epic group has 0 issues and includes the epic object
        empty_epic_group = next(g for g in result_with_project if g["epic_key"] == empty_epic.key)
        self.assertEqual(len(empty_epic_group["issues"]), 0)
        self.assertEqual(empty_epic_group["epic"], empty_epic)

    def test_group_by_epic_excludes_empty_epics_when_include_empty_epics_false(self):
        """When include_empty_epics=False, epics without matching issues should be excluded."""
        # Create an epic with no children
        empty_epic = EpicFactory(project=self.project, title="Empty Epic")

        # Get only non-epic issues (won't include the empty epic's children since there are none)
        issues = list(self._get_issues_queryset().filter(depth__gt=1))

        # With project but include_empty_epics=False, empty epic should NOT appear
        result = build_grouped_issues(issues, "epic", project=self.project, include_empty_epics=False)
        group_names = [group["name"] for group in result]
        self.assertNotIn(f"[{empty_epic.key}] {empty_epic.title}", group_names)

        # But epics with children should still appear
        self.assertIn(f"[{self.epic1.key}] {self.epic1.title}", group_names)
        self.assertIn(f"[{self.epic2.key}] {self.epic2.title}", group_names)


class CalculateProgressTest(TestCase):
    """Tests for calculate_progress() helper function."""

    def test_returns_none_for_empty_list(self):
        self.assertIsNone(calculate_progress([]))

    def test_all_todo_statuses(self):
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DRAFT)
        StoryFactory(project=project, parent=epic, status=IssueStatus.PLANNING)
        StoryFactory(project=project, parent=epic, status=IssueStatus.READY)

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["todo_pct"], 100)
        self.assertEqual(result["in_progress_pct"], 0)
        self.assertEqual(result["done_pct"], 0)
        self.assertEqual(result["total_weight"], 3)

    def test_all_done_statuses(self):
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DONE)
        StoryFactory(project=project, parent=epic, status=IssueStatus.ARCHIVED)

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["done_pct"], 100)
        self.assertEqual(result["todo_pct"], 0)
        self.assertEqual(result["in_progress_pct"], 0)

    def test_all_in_progress_statuses(self):
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.IN_PROGRESS)
        BugFactory(project=project, parent=epic, status=IssueStatus.BLOCKED)

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["in_progress_pct"], 100)
        self.assertEqual(result["todo_pct"], 0)
        self.assertEqual(result["done_pct"], 0)

    def test_mixed_statuses_equal_weight(self):
        """Each child with no estimated_points counts as weight=1."""
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DRAFT)
        StoryFactory(project=project, parent=epic, status=IssueStatus.IN_PROGRESS)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DONE)

        children = list(epic.get_children())
        result = calculate_progress(children)

        # done and in_progress are rounded; todo absorbs the remainder
        self.assertEqual(result["done_pct"], 33)
        self.assertEqual(result["in_progress_pct"], 33)
        self.assertEqual(result["todo_pct"], 34)
        self.assertEqual(result["done_pct"] + result["in_progress_pct"] + result["todo_pct"], 100)
        self.assertEqual(result["total_weight"], 3)

    def test_weighted_by_story_points(self):
        """Children with estimated_points use points as weight."""
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DONE, estimated_points=8)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DRAFT, estimated_points=2)

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["done_pct"], 80)
        self.assertEqual(result["todo_pct"], 20)
        self.assertEqual(result["done_weight"], 8)
        self.assertEqual(result["todo_weight"], 2)
        self.assertEqual(result["total_weight"], 10)

    def test_mixed_pointed_and_unpointed(self):
        """Children without points default to weight=1."""
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DONE, estimated_points=4)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DRAFT)  # weight=1

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["done_pct"], 80)
        self.assertEqual(result["todo_pct"], 20)
        self.assertEqual(result["total_weight"], 5)

    def test_zero_points_treated_as_one(self):
        """Children with estimated_points=0 should be treated as weight=1."""
        project = ProjectFactory()
        epic = EpicFactory(project=project)
        StoryFactory(project=project, parent=epic, status=IssueStatus.DONE, estimated_points=0)

        children = list(epic.get_children())
        result = calculate_progress(children)

        self.assertEqual(result["done_pct"], 100)
        self.assertEqual(result["total_weight"], 1)


class GetProgressModelMethodTest(TestCase):
    """Tests for BaseIssue.get_progress() model method."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()

    def test_epic_with_children(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            status=IssueStatus.DONE,
            estimated_points=3,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            status=IssueStatus.DRAFT,
            estimated_points=7,
        )

        result = epic.get_progress()

        self.assertIsNotNone(result)
        self.assertEqual(result["done_pct"], 30)
        self.assertEqual(result["todo_pct"], 70)
        self.assertEqual(result["total_weight"], 10)

    def test_epic_without_children(self):
        epic = EpicFactory(project=self.project)
        result = epic.get_progress()
        self.assertIsNone(result)

    def test_story_with_children(self):
        """get_progress() works on non-epic issues too."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)
        result = story.get_progress()
        # Stories typically have no children, so should return None
        self.assertIsNone(result)


class BuildGroupedIssuesProgressTest(TestCase):
    """Tests that build_grouped_issues() includes progress for epic groups."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project, title="Test Epic")
        StoryFactory(
            project=cls.project,
            parent=cls.epic,
            status=IssueStatus.DONE,
            estimated_points=5,
        )
        StoryFactory(
            project=cls.project,
            parent=cls.epic,
            status=IssueStatus.IN_PROGRESS,
            estimated_points=3,
        )
        StoryFactory(
            project=cls.project,
            parent=cls.epic,
            status=IssueStatus.DRAFT,
            estimated_points=2,
        )

    def test_epic_groups_include_progress(self):
        issues = list(BaseIssue.objects.for_project(self.project).select_related("project", "assignee"))
        result = build_grouped_issues(issues, "epic")

        epic_group = next(g for g in result if g["epic_key"] == self.epic.key)
        progress = epic_group["progress"]

        self.assertIsNotNone(progress)
        self.assertEqual(progress["done_pct"], 50)
        self.assertEqual(progress["in_progress_pct"], 30)
        self.assertEqual(progress["todo_pct"], 20)
        self.assertEqual(progress["total_weight"], 10)

    def test_empty_epic_group_has_none_progress(self):
        empty_epic = EpicFactory(project=self.project, title="Empty Epic")
        issues = list(
            BaseIssue.objects.for_project(self.project).filter(depth__gt=1).select_related("project", "assignee")
        )
        result = build_grouped_issues(issues, "epic", project=self.project)

        empty_group = next(g for g in result if g["epic_key"] == empty_epic.key)
        self.assertIsNone(empty_group["progress"])

    def test_non_epic_groups_do_not_include_progress(self):
        issues = list(BaseIssue.objects.for_project(self.project).select_related("project", "assignee"))
        result = build_grouped_issues(issues, "status")

        for group in result:
            self.assertNotIn("progress", group)


class BuildGroupedIssuesExcludeEpicsTest(TestCase):
    """Tests that build_grouped_issues() excludes epics from non-epic groupings."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.sprint = SprintFactory(workspace=cls.project.workspace)

        # Create an epic and some stories
        cls.epic = EpicFactory(project=cls.project, title="Test Epic")
        cls.story1 = StoryFactory(project=cls.project, parent=cls.epic, sprint=cls.sprint)
        cls.story2 = StoryFactory(project=cls.project, parent=cls.epic, sprint=None)

    def test_epics_excluded_from_sprint_grouping(self):
        """Epics should not appear as items when grouping by sprint."""
        # Get all issues including the epic
        issues = list(BaseIssue.objects.for_project(self.project))

        # Verify we have the epic in the queryset
        self.assertTrue(any(isinstance(issue, Epic) for issue in issues))

        result = build_grouped_issues(issues, "sprint")

        # Verify no epics appear in any group's issues list
        for group in result:
            for issue in group["issues"]:
                self.assertNotIsInstance(issue, Epic, "Epic should not appear in sprint groups")

        # Verify we still have stories in the groups
        all_grouped_issues = [issue for group in result for issue in group["issues"]]
        self.assertIn(self.story1, all_grouped_issues)
        self.assertIn(self.story2, all_grouped_issues)

    def test_epics_excluded_from_status_grouping(self):
        """Epics should not appear as items when grouping by status."""
        issues = list(BaseIssue.objects.for_project(self.project))
        result = build_grouped_issues(issues, "status")

        for group in result:
            for issue in group["issues"]:
                self.assertNotIsInstance(issue, Epic, "Epic should not appear in status groups")

    def test_epics_excluded_from_priority_grouping(self):
        """Epics should not appear as items when grouping by priority."""
        issues = list(BaseIssue.objects.for_project(self.project))
        result = build_grouped_issues(issues, "priority")

        for group in result:
            for issue in group["issues"]:
                self.assertNotIsInstance(issue, Epic, "Epic should not appear in priority groups")

    def test_epics_excluded_from_assignee_grouping(self):
        """Epics should not appear as items when grouping by assignee."""
        issues = list(BaseIssue.objects.for_project(self.project))
        result = build_grouped_issues(issues, "assignee")

        for group in result:
            for issue in group["issues"]:
                self.assertNotIsInstance(issue, Epic, "Epic should not appear in assignee groups")

    def test_epics_excluded_from_project_grouping(self):
        """Epics should not appear as items when grouping by project."""
        issues = list(BaseIssue.objects.for_project(self.project))
        result = build_grouped_issues(issues, "project")

        for group in result:
            for issue in group["issues"]:
                self.assertNotIsInstance(issue, Epic, "Epic should not appear in project groups")


class BuildGroupedIssuesEpicPriorityOrderTest(TestCase):
    """Tests that epic groups are ordered by priority (Critical first, Low last)."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.milestone = MilestoneFactory(project=cls.project)

        # Create epics with different priorities, in non-sorted order
        cls.epic_low = EpicFactory(
            project=cls.project,
            title="Low Priority Epic",
            priority=IssuePriority.LOW,
            milestone=cls.milestone,
        )
        cls.epic_critical = EpicFactory(
            project=cls.project,
            title="Critical Priority Epic",
            priority=IssuePriority.CRITICAL,
            milestone=cls.milestone,
        )
        cls.epic_medium = EpicFactory(
            project=cls.project,
            title="Medium Priority Epic",
            priority=IssuePriority.MEDIUM,
            milestone=cls.milestone,
        )
        cls.epic_high = EpicFactory(
            project=cls.project,
            title="High Priority Epic",
            priority=IssuePriority.HIGH,
            milestone=cls.milestone,
        )

        # Add a story to each epic so they appear in non-empty grouping too
        for epic in [cls.epic_low, cls.epic_critical, cls.epic_medium, cls.epic_high]:
            StoryFactory(project=cls.project, parent=epic)

    def test_epic_groups_ordered_by_priority_critical_first(self):
        """Epic groups should be ordered from Critical to Low priority."""
        issues = list(BaseIssue.objects.for_project(self.project).filter(depth__gt=1))
        result = build_grouped_issues(issues, "epic", project=self.project)

        epic_priorities = [g["epic"].priority for g in result if g.get("epic")]

        self.assertEqual(
            epic_priorities,
            [
                IssuePriority.CRITICAL,
                IssuePriority.HIGH,
                IssuePriority.MEDIUM,
                IssuePriority.LOW,
            ],
        )

    def test_epic_groups_ordered_by_priority_with_milestone(self):
        """Epic groups from milestone should also be ordered by priority."""
        issues = list(BaseIssue.objects.for_project(self.project).filter(depth__gt=1))
        result = build_grouped_issues(issues, "epic", milestone=self.milestone)

        epic_priorities = [g["epic"].priority for g in result if g.get("epic")]

        self.assertEqual(
            epic_priorities,
            [
                IssuePriority.CRITICAL,
                IssuePriority.HIGH,
                IssuePriority.MEDIUM,
                IssuePriority.LOW,
            ],
        )

    def test_no_epic_group_sorted_last(self):
        """The 'No Epic' group should appear after all priority-sorted epic groups."""
        # Create a story without a parent epic
        orphan_story = StoryFactory(project=self.project)

        issues = list(BaseIssue.objects.for_project(self.project).filter(depth__gt=1))
        # Add the orphan (depth=1) manually since it's a root story
        issues.append(orphan_story)

        result = build_grouped_issues(issues, "epic", project=self.project)

        # Last group should be "No Epic"
        self.assertIsNone(result[-1]["epic"])
        # All other groups should have epics sorted by priority
        epic_priorities = [g["epic"].priority for g in result[:-1] if g.get("epic")]
        self.assertEqual(
            epic_priorities,
            [
                IssuePriority.CRITICAL,
                IssuePriority.HIGH,
                IssuePriority.MEDIUM,
                IssuePriority.LOW,
            ],
        )
