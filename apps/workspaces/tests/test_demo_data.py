from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.issues.models import BaseIssue, Bug, BugSeverity, Chore, Epic, IssueStatus, Milestone, Story, Subtask
from apps.projects.models import ProjectStatus
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.tests.base import WorkspaceTestMixin
from apps.workspaces.demo_data import (
    SPRINT_ACTIVE_ITEMS,
    SPRINT_COMPLETED_ITEMS,
    SPRINT_PLANNING_ITEMS,
    SUBTASKS,
    create_demo_project,
)


class CreateDemoProjectTest(WorkspaceTestMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.project = create_demo_project(cls.workspace, cls.admin)

    def test_project_created_with_correct_attributes(self):
        self.assertEqual(self.project.name, "Acme SaaS Platform")
        self.assertEqual(self.project.status, ProjectStatus.ACTIVE)
        self.assertEqual(self.project.workspace, self.workspace)
        self.assertEqual(self.project.lead, self.admin)
        self.assertIsNone(self.project.created_by)

    def test_demo_project_has_no_created_by(self):
        self.assertIsNone(self.project.created_by)

    def test_creates_four_milestones(self):
        milestones = Milestone.objects.filter(project=self.project)
        self.assertEqual(milestones.count(), 4)

    def test_milestone_titles(self):
        titles = set(Milestone.objects.filter(project=self.project).values_list("title", flat=True))
        self.assertEqual(titles, {"Private Alpha", "Private Beta", "Public Beta", "Public Launch"})

    def test_milestone_statuses(self):
        milestones = {m.title: m for m in Milestone.objects.filter(project=self.project)}
        self.assertEqual(milestones["Private Alpha"].status, IssueStatus.DONE)
        self.assertEqual(milestones["Private Beta"].status, IssueStatus.IN_PROGRESS)
        self.assertEqual(milestones["Public Beta"].status, IssueStatus.PLANNING)
        self.assertEqual(milestones["Public Launch"].status, IssueStatus.DRAFT)

    def test_milestones_have_owner_and_no_created_by(self):
        for milestone in Milestone.objects.filter(project=self.project):
            self.assertEqual(
                milestone.owner,
                self.admin,
                f"Milestone '{milestone.title}' missing owner",
            )
            self.assertIsNone(
                milestone.created_by,
                f"Milestone '{milestone.title}' should have no created_by",
            )

    def test_milestone_keys_are_sequential(self):
        keys = list(Milestone.objects.filter(project=self.project).order_by("key").values_list("key", flat=True))
        self.assertEqual(keys, ["M-1", "M-2", "M-3", "M-4"])

    def test_creates_eleven_epics(self):
        epics = Epic.objects.filter(project=self.project)
        self.assertEqual(epics.count(), 11)

    def test_epics_are_root_nodes(self):
        for epic in Epic.objects.filter(project=self.project):
            self.assertEqual(epic.depth, 1, f"Epic '{epic.title}' is not a root node")

    def test_epics_linked_to_milestones(self):
        for epic in Epic.objects.filter(project=self.project).select_related("milestone"):
            self.assertIsNotNone(epic.milestone, f"Epic '{epic.title}' has no milestone")

    def test_epics_have_assignee_and_no_created_by(self):
        for epic in Epic.objects.filter(project=self.project):
            self.assertEqual(epic.assignee, self.admin, f"Epic '{epic.title}' missing assignee")
            self.assertIsNone(epic.created_by, f"Epic '{epic.title}' should have no created_by")

    def test_creates_work_items(self):
        stories = Story.objects.filter(project=self.project).count()
        bugs = Bug.objects.filter(project=self.project).count()
        chores = Chore.objects.filter(project=self.project).count()
        total = stories + bugs + chores
        self.assertGreaterEqual(total, 40)
        self.assertGreater(stories, 0)
        self.assertGreater(bugs, 0)
        self.assertGreater(chores, 0)

    def test_work_items_are_children_of_epics(self):
        for item in BaseIssue.objects.filter(project=self.project, depth=2):
            parent = item.get_parent()
            self.assertIsNotNone(parent)
            self.assertIsInstance(parent, Epic)

    def test_work_items_have_estimated_points(self):
        for item in BaseIssue.objects.filter(project=self.project, depth=2):
            self.assertIsNotNone(item.estimated_points, f"Item '{item.title}' has no estimated_points")
            self.assertIn(item.estimated_points, [1, 2, 3, 5, 8])

    def test_work_items_have_assignee_and_no_created_by(self):
        for item in BaseIssue.objects.filter(project=self.project, depth=2):
            self.assertEqual(item.assignee, self.admin, f"Item '{item.title}' missing assignee")
            self.assertIsNone(item.created_by, f"Item '{item.title}' should have no created_by")

    def test_bugs_have_severity(self):
        for bug in Bug.objects.filter(project=self.project):
            self.assertIn(
                bug.severity,
                BugSeverity.values,
                f"Bug '{bug.title}' has invalid severity",
            )

    def test_creates_three_sprints(self):
        sprints = Sprint.objects.filter(workspace=self.workspace)
        self.assertEqual(sprints.count(), 3)

    def test_sprint_statuses(self):
        statuses = set(Sprint.objects.filter(workspace=self.workspace).values_list("status", flat=True))
        self.assertEqual(
            statuses,
            {SprintStatus.COMPLETED, SprintStatus.ACTIVE, SprintStatus.PLANNING},
        )

    def test_only_one_active_sprint(self):
        active_count = Sprint.objects.filter(workspace=self.workspace, status=SprintStatus.ACTIVE).count()
        self.assertEqual(active_count, 1)

    def test_sprint_keys_are_sequential(self):
        keys = list(Sprint.objects.filter(workspace=self.workspace).order_by("key").values_list("key", flat=True))
        self.assertEqual(keys, ["SPRINT-1", "SPRINT-2", "SPRINT-3"])

    def test_sprint_dates_are_valid(self):
        for sprint in Sprint.objects.filter(workspace=self.workspace):
            self.assertGreater(
                sprint.end_date,
                sprint.start_date,
                f"Sprint '{sprint.name}' has invalid dates",
            )
            duration = (sprint.end_date - sprint.start_date).days
            self.assertGreaterEqual(duration, 7, f"Sprint '{sprint.name}' is too short ({duration} days)")

    def test_completed_sprint_items_are_done(self):
        completed_sprint = Sprint.objects.get(workspace=self.workspace, status=SprintStatus.COMPLETED)
        items = BaseIssue.objects.filter(story__sprint=completed_sprint) | BaseIssue.objects.filter(
            bug__sprint=completed_sprint
        )
        self.assertEqual(items.count(), len(SPRINT_COMPLETED_ITEMS))
        for item in items:
            self.assertEqual(
                item.status,
                IssueStatus.DONE,
                f"Completed sprint item '{item.title}' is not DONE",
            )

    def test_active_sprint_has_mixed_statuses(self):
        active_sprint = Sprint.objects.get(workspace=self.workspace, status=SprintStatus.ACTIVE)
        # Query across work item types
        story_items = Story.objects.filter(sprint=active_sprint)
        bug_items = Bug.objects.filter(sprint=active_sprint)
        all_items = list(story_items) + list(bug_items)
        self.assertEqual(len(all_items), len(SPRINT_ACTIVE_ITEMS))
        statuses = {item.status for item in all_items}
        self.assertTrue(len(statuses) > 1, "Active sprint should have mixed statuses")

    def test_planning_sprint_items_are_planning(self):
        planning_sprint = Sprint.objects.get(workspace=self.workspace, status=SprintStatus.PLANNING)
        items = Story.objects.filter(sprint=planning_sprint)
        self.assertEqual(items.count(), len(SPRINT_PLANNING_ITEMS))
        for item in items:
            self.assertEqual(
                item.status,
                IssueStatus.PLANNING,
                f"Planning sprint item '{item.title}' is not PLANNING",
            )

    def test_completed_sprint_velocity(self):
        completed_sprint = Sprint.objects.get(workspace=self.workspace, status=SprintStatus.COMPLETED)
        self.assertGreater(completed_sprint.committed_points, 0)
        self.assertEqual(completed_sprint.committed_points, completed_sprint.completed_points)

    def test_active_sprint_velocity(self):
        active_sprint = Sprint.objects.get(workspace=self.workspace, status=SprintStatus.ACTIVE)
        self.assertGreater(active_sprint.committed_points, 0)
        self.assertGreater(active_sprint.completed_points, 0)
        self.assertLess(active_sprint.completed_points, active_sprint.committed_points)

    def test_subtasks_created(self):
        expected_count = sum(len(tasks) for tasks in SUBTASKS.values())
        total_subtasks = Subtask.objects.count()
        self.assertEqual(total_subtasks, expected_count)

    def test_subtasks_on_correct_items(self):
        for item_title in SUBTASKS:
            item = BaseIssue.objects.get(project=self.project, title=item_title)
            ct = ContentType.objects.get_for_model(item)
            subtask_count = Subtask.objects.filter(content_type=ct, object_id=item.pk).count()
            self.assertEqual(
                subtask_count,
                len(SUBTASKS[item_title]),
                f"Wrong subtask count for '{item_title}'",
            )

    def test_demo_items_have_no_created_by(self):
        items_with_creator = BaseIssue.objects.filter(project=self.project, created_by__isnull=False).count()
        self.assertEqual(items_with_creator, 0)
