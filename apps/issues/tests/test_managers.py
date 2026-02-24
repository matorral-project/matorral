from datetime import date, timedelta

from django.test import TestCase

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, MilestoneFactory, StoryFactory
from apps.issues.models import BaseIssue, Bug, Epic, IssueStatus, Milestone, Story
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.users.factories import CustomUserFactory
from apps.workspaces.factories import WorkspaceFactory


class IssueQuerySetForProjectTest(TestCase):
    """Tests for for_project filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project1 = ProjectFactory()
        cls.project2 = ProjectFactory()
        cls.epic1 = EpicFactory(project=cls.project1)
        cls.epic2 = EpicFactory(project=cls.project2)

    def test_for_project_filters_by_project(self):
        """for_project returns only issues in the given project."""
        issues = BaseIssue.objects.for_project(self.project1)

        self.assertEqual(1, issues.count())
        self.assertIn(self.epic1, issues)
        self.assertNotIn(self.epic2, issues)


class IssueQuerySetForWorkspaceTest(TestCase):
    """Tests for for_workspace filter."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace1 = WorkspaceFactory()
        cls.workspace2 = WorkspaceFactory()
        cls.project1 = ProjectFactory(workspace=cls.workspace1)
        cls.project2 = ProjectFactory(workspace=cls.workspace2)
        cls.epic1 = EpicFactory(project=cls.project1)
        cls.epic2 = EpicFactory(project=cls.project2)

    def test_for_workspace_filters_by_workspace(self):
        """for_workspace returns only issues in projects belonging to the workspace."""
        issues = BaseIssue.objects.for_workspace(self.workspace1)

        self.assertEqual(1, issues.count())
        self.assertIn(self.epic1, issues)
        self.assertNotIn(self.epic2, issues)


class IssueQuerySetOfTypeTest(TestCase):
    """Tests for of_type filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project)
        cls.story = StoryFactory(project=cls.project, parent=cls.epic)
        cls.bug = BugFactory(project=cls.project, parent=cls.epic)

    def test_of_type_single_type(self):
        """of_type filters to a single issue type."""
        epics = BaseIssue.objects.for_project(self.project).of_type(Epic)

        self.assertEqual(1, epics.count())
        self.assertIn(self.epic, epics)

    def test_of_type_multiple_types(self):
        """of_type filters to multiple issue types."""
        issues = BaseIssue.objects.for_project(self.project).of_type(Story, Bug)

        self.assertEqual(2, issues.count())
        self.assertIn(self.story, issues)
        self.assertIn(self.bug, issues)


class IssueQuerySetWorkItemsTest(TestCase):
    """Tests for work_items filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project)
        cls.story = StoryFactory(project=cls.project, parent=cls.epic)
        cls.bug = BugFactory(project=cls.project, parent=cls.epic)
        cls.chore = ChoreFactory(project=cls.project, parent=cls.epic)

    def test_work_items_excludes_epics(self):
        """work_items returns only Story, Bug, and Chore types."""
        work_items = BaseIssue.objects.for_project(self.project).work_items()

        self.assertEqual(3, work_items.count())
        self.assertNotIn(self.epic, work_items)
        self.assertIn(self.story, work_items)
        self.assertIn(self.bug, work_items)
        self.assertIn(self.chore, work_items)


class IssueQuerySetBacklogTest(TestCase):
    """Tests for backlog filter (issues not in any sprint)."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.sprint = SprintFactory(workspace=cls.workspace)
        cls.epic = EpicFactory(project=cls.project)
        cls.story_in_sprint = StoryFactory(project=cls.project, parent=cls.epic, sprint=cls.sprint)
        cls.story_no_sprint = StoryFactory(project=cls.project, parent=cls.epic, sprint=None)
        cls.bug_in_sprint = BugFactory(project=cls.project, parent=cls.epic, sprint=cls.sprint)
        cls.bug_no_sprint = BugFactory(project=cls.project, parent=cls.epic, sprint=None)
        cls.chore_no_sprint = ChoreFactory(project=cls.project, parent=cls.epic, sprint=None)

    def test_backlog_returns_work_items_without_sprint(self):
        """backlog returns only work items that are not in any sprint."""
        backlog = BaseIssue.objects.for_project(self.project).backlog()

        self.assertEqual(3, backlog.count())
        self.assertIn(self.story_no_sprint, backlog)
        self.assertIn(self.bug_no_sprint, backlog)
        self.assertIn(self.chore_no_sprint, backlog)

    def test_backlog_excludes_items_in_sprint(self):
        """backlog excludes work items that are assigned to a sprint."""
        backlog = BaseIssue.objects.for_project(self.project).backlog()

        self.assertNotIn(self.story_in_sprint, backlog)
        self.assertNotIn(self.bug_in_sprint, backlog)

    def test_backlog_excludes_epics(self):
        """backlog excludes epics (they don't have sprints)."""
        backlog = BaseIssue.objects.for_project(self.project).backlog()

        self.assertNotIn(self.epic, backlog)


class IssueQuerySetRootsTest(TestCase):
    """Tests for roots filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project)
        cls.story = StoryFactory(project=cls.project, parent=cls.epic)

    def test_roots_returns_only_root_issues(self):
        """roots returns only issues with depth=1."""
        roots = BaseIssue.objects.for_project(self.project).roots()

        self.assertEqual(1, roots.count())
        self.assertIn(self.epic, roots)
        self.assertNotIn(self.story, roots)


class IssueQuerySetStatusFilterTest(TestCase):
    """Tests for status filters."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.draft = EpicFactory(project=cls.project, status=IssueStatus.DRAFT)
        cls.in_progress = EpicFactory(project=cls.project, status=IssueStatus.IN_PROGRESS)
        cls.done = EpicFactory(project=cls.project, status=IssueStatus.DONE)
        cls.archived = EpicFactory(project=cls.project, status=IssueStatus.ARCHIVED)

    def test_with_status_filters_to_specific_status(self):
        """with_status returns only issues with the given status."""
        issues = BaseIssue.objects.for_project(self.project).with_status(IssueStatus.DRAFT)

        self.assertEqual(1, issues.count())
        self.assertIn(self.draft, issues)

    def test_active_excludes_done_and_archived(self):
        """active excludes done and archived issues."""
        issues = BaseIssue.objects.for_project(self.project).active()

        self.assertEqual(2, issues.count())
        self.assertIn(self.draft, issues)
        self.assertIn(self.in_progress, issues)
        self.assertNotIn(self.done, issues)
        self.assertNotIn(self.archived, issues)


class IssueQuerySetSearchTest(TestCase):
    """Tests for search filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic1 = EpicFactory(project=cls.project, title="Release 1.0")
        cls.epic2 = EpicFactory(project=cls.project, title="Sprint Planning")

    def test_search_by_title(self):
        """search finds issues by title (case-insensitive)."""
        issues = BaseIssue.objects.for_project(self.project).search("release")

        self.assertEqual(1, issues.count())
        self.assertIn(self.epic1, issues)

    def test_search_by_key(self):
        """search finds issues by key."""
        issues = BaseIssue.objects.for_project(self.project).search(self.epic1.key)

        self.assertEqual(1, issues.count())
        self.assertIn(self.epic1, issues)

    def test_search_empty_returns_all(self):
        """Empty search returns all issues."""
        issues = BaseIssue.objects.for_project(self.project).search("")

        self.assertEqual(2, issues.count())


class IssueQuerySetAssigneeFilterTest(TestCase):
    """Tests for assignee filters."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.user = CustomUserFactory()
        cls.epic = EpicFactory(project=cls.project)
        cls.assigned_story = StoryFactory(project=cls.project, parent=cls.epic, assignee=cls.user)
        cls.unassigned_story = StoryFactory(project=cls.project, parent=cls.epic, assignee=None)

    def test_with_assignee_filters_by_user(self):
        """with_assignee returns stories assigned to the given user."""
        # Query directly on Story model since assignee is on work items
        issues = Story.objects.for_project(self.project).with_assignee(self.user)

        self.assertEqual(1, issues.count())
        self.assertIn(self.assigned_story, issues)

    def test_unassigned_returns_issues_without_assignee(self):
        """unassigned returns stories without an assignee."""
        # Query directly on Story model since assignee is on work items
        issues = Story.objects.for_project(self.project).unassigned()

        self.assertIn(self.unassigned_story, issues)


class IssueQuerySetOverdueTest(TestCase):
    """Tests for overdue filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        today = date.today()
        cls.overdue = EpicFactory(project=cls.project, due_date=today - timedelta(days=1))
        cls.not_overdue = EpicFactory(project=cls.project, due_date=today + timedelta(days=1))
        cls.done_overdue = EpicFactory(
            project=cls.project,
            due_date=today - timedelta(days=1),
            status=IssueStatus.DONE,
        )

    def test_overdue_returns_past_due_active_issues(self):
        """overdue returns issues with due_date in past that are not done/archived."""
        issues = BaseIssue.objects.for_project(self.project).overdue()

        self.assertEqual(1, issues.count())
        self.assertIn(self.overdue, issues)
        self.assertNotIn(self.done_overdue, issues)


class IssueQuerySetWithKeyTest(TestCase):
    """Tests for with_key filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project)

    def test_with_key_finds_issue(self):
        """with_key finds issue by exact key."""
        issues = BaseIssue.objects.for_project(self.project).with_key(self.epic.key)

        self.assertEqual(1, issues.count())
        self.assertIn(self.epic, issues)

    def test_with_key_exclude_works(self):
        """with_key can exclude a specific instance."""
        issues = BaseIssue.objects.for_project(self.project).with_key(self.epic.key, exclude=self.epic)

        self.assertEqual(0, issues.count())


class IssueQuerySetSetStatusTest(TestCase):
    """Tests for set_status bulk update."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()

    def test_set_status_updates_all(self):
        """set_status bulk updates status for all issues in queryset."""
        EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        EpicFactory(project=self.project, status=IssueStatus.DRAFT)

        count = BaseIssue.objects.for_project(self.project).set_status(IssueStatus.IN_PROGRESS)

        self.assertEqual(2, count)
        self.assertEqual(
            2,
            BaseIssue.objects.for_project(self.project).with_status(IssueStatus.IN_PROGRESS).count(),
        )


class MilestoneQuerySetForProjectTest(TestCase):
    """Tests for Milestone for_project filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project1 = ProjectFactory()
        cls.project2 = ProjectFactory()
        cls.milestone1 = MilestoneFactory(project=cls.project1)
        cls.milestone2 = MilestoneFactory(project=cls.project2)

    def test_for_project_filters_by_project(self):
        """for_project returns only milestones in the given project."""
        milestones = Milestone.objects.for_project(self.project1)

        self.assertEqual(1, milestones.count())
        self.assertIn(self.milestone1, milestones)
        self.assertNotIn(self.milestone2, milestones)


class MilestoneQuerySetSearchTest(TestCase):
    """Tests for Milestone search filter."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.milestone1 = MilestoneFactory(project=cls.project, title="Release 1.0")
        cls.milestone2 = MilestoneFactory(project=cls.project, title="Sprint Planning")

    def test_search_by_title(self):
        """search finds milestones by title (case-insensitive)."""
        milestones = Milestone.objects.for_project(self.project).search("release")

        self.assertEqual(1, milestones.count())
        self.assertIn(self.milestone1, milestones)

    def test_search_by_key(self):
        """search finds milestones by key."""
        milestones = Milestone.objects.for_project(self.project).search(self.milestone1.key)

        self.assertEqual(1, milestones.count())
        self.assertIn(self.milestone1, milestones)


class MilestoneQuerySetStatusFilterTest(TestCase):
    """Tests for Milestone status filters."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.draft = MilestoneFactory(project=cls.project, status=IssueStatus.DRAFT)
        cls.in_progress = MilestoneFactory(project=cls.project, status=IssueStatus.IN_PROGRESS)
        cls.done = MilestoneFactory(project=cls.project, status=IssueStatus.DONE)
        cls.archived = MilestoneFactory(project=cls.project, status=IssueStatus.ARCHIVED)

    def test_with_status_filters_to_specific_status(self):
        """with_status returns only milestones with the given status."""
        milestones = Milestone.objects.for_project(self.project).with_status(IssueStatus.DRAFT)

        self.assertEqual(1, milestones.count())
        self.assertIn(self.draft, milestones)

    def test_active_excludes_done_and_archived(self):
        """active excludes done and archived milestones."""
        milestones = Milestone.objects.for_project(self.project).active()

        self.assertEqual(2, milestones.count())
        self.assertIn(self.draft, milestones)
        self.assertIn(self.in_progress, milestones)
        self.assertNotIn(self.done, milestones)
        self.assertNotIn(self.archived, milestones)
