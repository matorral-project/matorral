"""Unit tests for the cascade status change service."""

from django.test import TestCase

from apps.issues.cascade import (
    apply_cascade,
    check_cascade_opportunities,
    get_children_for_cascade,
    get_parent_and_siblings,
    map_status_for_cascade_up,
)
from apps.issues.factories import EpicFactory, MilestoneFactory, StoryFactory, SubtaskFactory
from apps.issues.models import IssueStatus, SubtaskStatus
from apps.projects.factories import ProjectFactory
from apps.projects.models import ProjectStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import WorkspaceFactory


class GetChildrenForCascadeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_project_children_are_milestones_and_orphan_epics(self):
        milestone = MilestoneFactory(project=self.project)
        epic_with_milestone = EpicFactory(project=self.project, milestone=milestone)
        orphan_epic = EpicFactory(project=self.project, milestone=None)

        children, child_type = get_children_for_cascade(self.project)

        child_pks = {c.pk for c in children}
        self.assertIn(milestone.pk, child_pks)
        self.assertIn(orphan_epic.pk, child_pks)
        # Epic with milestone is NOT an orphan, so it should NOT be in project children
        self.assertNotIn(epic_with_milestone.pk, child_pks)

    def test_milestone_children_are_its_epics(self):
        milestone = MilestoneFactory(project=self.project)
        epic1 = EpicFactory(project=self.project, milestone=milestone)
        epic2 = EpicFactory(project=self.project, milestone=milestone)
        _other_epic = EpicFactory(project=self.project, milestone=None)

        children, child_type = get_children_for_cascade(milestone)

        child_pks = {c.pk for c in children}
        self.assertEqual(child_pks, {epic1.pk, epic2.pk})
        self.assertEqual(child_type, "issue")

    def test_epic_children_are_treebeard_children(self):
        epic = EpicFactory(project=self.project)
        story1 = StoryFactory(project=self.project, parent=epic)
        story2 = StoryFactory(project=self.project, parent=epic)

        children, child_type = get_children_for_cascade(epic)

        child_pks = {c.pk for c in children}
        self.assertEqual(child_pks, {story1.pk, story2.pk})
        self.assertEqual(child_type, "issue")

    def test_work_item_children_are_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask1 = SubtaskFactory(parent=story)
        subtask2 = SubtaskFactory(parent=story)

        children, child_type = get_children_for_cascade(story)

        child_pks = {c.pk for c in children}
        self.assertEqual(child_pks, {subtask1.pk, subtask2.pk})
        self.assertEqual(child_type, "subtask")

    def test_subtask_has_no_children(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story)

        children, child_type = get_children_for_cascade(subtask)

        self.assertEqual(children, [])
        self.assertEqual(child_type, "none")


class GetParentAndSiblingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_subtask_parent_is_work_item(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask1 = SubtaskFactory(parent=story)
        subtask2 = SubtaskFactory(parent=story)

        parent, siblings = get_parent_and_siblings(subtask1)

        self.assertEqual(parent.pk, story.pk)
        sibling_pks = {s.pk for s in siblings}
        self.assertIn(subtask2.pk, sibling_pks)
        self.assertNotIn(subtask1.pk, sibling_pks)

    def test_work_item_parent_is_epic(self):
        epic = EpicFactory(project=self.project)
        story1 = StoryFactory(project=self.project, parent=epic)
        story2 = StoryFactory(project=self.project, parent=epic)

        parent, siblings = get_parent_and_siblings(story1)

        self.assertEqual(parent.pk, epic.pk)
        sibling_pks = {s.pk for s in siblings}
        self.assertIn(story2.pk, sibling_pks)

    def test_epic_with_milestone_parent_is_milestone(self):
        milestone = MilestoneFactory(project=self.project)
        epic1 = EpicFactory(project=self.project, milestone=milestone)
        epic2 = EpicFactory(project=self.project, milestone=milestone)

        parent, siblings = get_parent_and_siblings(epic1)

        self.assertEqual(parent.pk, milestone.pk)
        sibling_pks = {s.pk for s in siblings}
        self.assertIn(epic2.pk, sibling_pks)

    def test_orphan_epic_parent_is_project(self):
        orphan = EpicFactory(project=self.project, milestone=None)
        milestone = MilestoneFactory(project=self.project)

        parent, siblings = get_parent_and_siblings(orphan)

        self.assertEqual(parent.pk, self.project.pk)
        # Siblings include milestones
        sibling_pks = {s.pk for s in siblings}
        self.assertIn(milestone.pk, sibling_pks)

    def test_milestone_parent_is_project(self):
        milestone1 = MilestoneFactory(project=self.project)
        milestone2 = MilestoneFactory(project=self.project)
        orphan_epic = EpicFactory(project=self.project, milestone=None)

        parent, siblings = get_parent_and_siblings(milestone1)

        self.assertEqual(parent.pk, self.project.pk)
        sibling_pks = {s.pk for s in siblings}
        self.assertIn(milestone2.pk, sibling_pks)
        self.assertIn(orphan_epic.pk, sibling_pks)

    def test_root_work_item_has_no_parent(self):
        story = StoryFactory(project=self.project, parent=None)

        parent, siblings = get_parent_and_siblings(story)

        self.assertIsNone(parent)


class MapStatusForCascadeUpTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.milestone = MilestoneFactory(project=cls.project)

    def test_issue_done_to_project(self):
        result = map_status_for_cascade_up(IssueStatus.DONE, self.project)
        self.assertEqual(result, ProjectStatus.COMPLETED)

    def test_issue_archived_to_project(self):
        result = map_status_for_cascade_up(IssueStatus.ARCHIVED, self.project)
        self.assertEqual(result, ProjectStatus.ARCHIVED)

    def test_issue_wont_do_to_project(self):
        result = map_status_for_cascade_up(IssueStatus.WONT_DO, self.project)
        self.assertEqual(result, ProjectStatus.COMPLETED)

    def test_issue_done_to_milestone(self):
        result = map_status_for_cascade_up(IssueStatus.DONE, self.milestone)
        self.assertEqual(result, IssueStatus.DONE)

    def test_issue_archived_to_milestone(self):
        result = map_status_for_cascade_up(IssueStatus.ARCHIVED, self.milestone)
        self.assertEqual(result, IssueStatus.ARCHIVED)

    def test_subtask_done_to_issue(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        result = map_status_for_cascade_up(SubtaskStatus.DONE, story)
        self.assertEqual(result, IssueStatus.DONE)

    def test_subtask_wont_do_to_issue(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        result = map_status_for_cascade_up(SubtaskStatus.WONT_DO, story)
        self.assertEqual(result, IssueStatus.WONT_DO)

    def test_issue_in_progress_to_milestone(self):
        result = map_status_for_cascade_up(IssueStatus.IN_PROGRESS, self.milestone)
        self.assertEqual(result, IssueStatus.IN_PROGRESS)

    def test_issue_in_progress_to_project(self):
        result = map_status_for_cascade_up(IssueStatus.IN_PROGRESS, self.project)
        self.assertEqual(result, ProjectStatus.ACTIVE)

    def test_subtask_in_progress_to_issue(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        result = map_status_for_cascade_up(SubtaskStatus.IN_PROGRESS, story)
        self.assertEqual(result, IssueStatus.IN_PROGRESS)


class CheckCascadeDownTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_epic_done_offers_to_complete_draft_children(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        info = check_cascade_opportunities(epic, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.children), 1)
        self.assertEqual(info.cascade_down.children[0].pk, story.pk)
        self.assertEqual(info.cascade_down.target_status, IssueStatus.DONE)

    def test_epic_done_skips_already_completed_children(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)

        info = check_cascade_opportunities(epic, IssueStatus.DONE)

        self.assertIsNone(info.cascade_down)

    def test_epic_archived_offers_to_archive_non_completed_children(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)

        info = check_cascade_opportunities(epic, IssueStatus.ARCHIVED)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(info.cascade_down.target_status, IssueStatus.ARCHIVED)

    def test_epic_planning_only_moves_draft_children(self):
        epic = EpicFactory(project=self.project)
        draft_story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        _planning_story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.PLANNING)

        info = check_cascade_opportunities(epic, IssueStatus.PLANNING)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.children), 1)
        self.assertEqual(info.cascade_down.children[0].pk, draft_story.pk)

    def test_epic_ready_moves_draft_and_planning_children(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.PLANNING)
        _in_progress = StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)

        info = check_cascade_opportunities(epic, IssueStatus.READY)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.children), 2)

    def test_epic_in_progress_does_not_cascade_down(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.PLANNING)

        info = check_cascade_opportunities(epic, IssueStatus.IN_PROGRESS)

        self.assertIsNone(info.cascade_down)

    def test_no_cascade_down_when_no_children(self):
        epic = EpicFactory(project=self.project)

        info = check_cascade_opportunities(epic, IssueStatus.DONE)

        self.assertIsNone(info.cascade_down)

    def test_project_completed_cascades_to_milestones_and_orphan_epics(self):
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)
        orphan_epic = EpicFactory(project=self.project, milestone=None, status=IssueStatus.DRAFT)

        info = check_cascade_opportunities(self.project, ProjectStatus.COMPLETED)

        self.assertIsNotNone(info.cascade_down)
        child_pks = {c.pk for c in info.cascade_down.children}
        self.assertIn(milestone.pk, child_pks)
        self.assertIn(orphan_epic.pk, child_pks)
        self.assertEqual(info.cascade_down.target_status, IssueStatus.DONE)

    def test_project_archived_cascades_to_children(self):
        MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        info = check_cascade_opportunities(self.project, ProjectStatus.ARCHIVED)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(info.cascade_down.target_status, IssueStatus.ARCHIVED)

    def test_work_item_done_cascades_to_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(story, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.children), 1)
        self.assertEqual(info.cascade_down.children[0].pk, subtask.pk)
        self.assertEqual(info.cascade_down.target_status, SubtaskStatus.DONE)

    def test_work_item_in_progress_does_not_cascade_down_to_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story, status=SubtaskStatus.TODO)
        SubtaskFactory(parent=story, status=SubtaskStatus.DONE)

        info = check_cascade_opportunities(story, IssueStatus.IN_PROGRESS)

        self.assertIsNone(info.cascade_down)

    def test_no_subtask_cascade_for_planning_status(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(story, IssueStatus.PLANNING)

        # PLANNING has no SubtaskStatus equivalent
        self.assertIsNone(info.cascade_down)


class CheckCascadeUpTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_last_sibling_done_offers_parent_completion(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)
        story2 = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)

        info = check_cascade_opportunities(story2, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_up)
        self.assertEqual(info.cascade_up.parent.pk, epic.pk)
        self.assertEqual(info.cascade_up.suggested_status, IssueStatus.DONE)

    def test_no_cascade_up_when_siblings_not_all_completed(self):
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)
        story2 = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)

        info = check_cascade_opportunities(story2, IssueStatus.DONE)

        self.assertIsNone(info.cascade_up)

    def test_no_cascade_up_when_parent_already_completed(self):
        epic = EpicFactory(project=self.project, status=IssueStatus.DONE)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)

        info = check_cascade_opportunities(story, IssueStatus.DONE)

        self.assertIsNone(info.cascade_up)

    def test_in_progress_bubbles_up_when_parent_is_earlier_status(self):
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)

        info = check_cascade_opportunities(story, IssueStatus.IN_PROGRESS)

        self.assertIsNotNone(info.cascade_up)
        self.assertEqual(info.cascade_up.parent.pk, epic.pk)
        self.assertEqual(info.cascade_up.suggested_status, IssueStatus.IN_PROGRESS)

    def test_no_cascade_up_for_in_progress_when_parent_already_in_progress(self):
        epic = EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.IN_PROGRESS)

        info = check_cascade_opportunities(story, IssueStatus.IN_PROGRESS)

        self.assertIsNone(info.cascade_up)

    def test_no_cascade_up_for_planning_status(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.PLANNING)

        info = check_cascade_opportunities(story, IssueStatus.PLANNING)

        self.assertIsNone(info.cascade_up)

    def test_all_milestones_and_orphan_epics_done_offers_project_completion(self):
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DONE)
        EpicFactory(project=self.project, milestone=None, status=IssueStatus.DONE)

        info = check_cascade_opportunities(milestone, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_up)
        self.assertEqual(info.cascade_up.parent.pk, self.project.pk)
        self.assertEqual(info.cascade_up.suggested_status, ProjectStatus.COMPLETED)

    def test_subtask_done_with_all_siblings_offers_parent_completion(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story, status=SubtaskStatus.DONE)
        subtask2 = SubtaskFactory(parent=story, status=SubtaskStatus.DONE)

        info = check_cascade_opportunities(subtask2, SubtaskStatus.DONE)

        self.assertIsNotNone(info.cascade_up)
        self.assertEqual(info.cascade_up.parent.pk, story.pk)
        self.assertEqual(info.cascade_up.suggested_status, IssueStatus.DONE)

    def test_both_cascade_down_and_up(self):
        """An epic set to DONE can cascade both down to children and up to milestone."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DONE)
        epic2 = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DONE)
        # epic2 has a draft child (cascade down) and all epics under milestone are done (cascade up)
        StoryFactory(project=self.project, parent=epic2, status=IssueStatus.DRAFT)

        info = check_cascade_opportunities(epic2, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.children), 1)
        self.assertIsNotNone(info.cascade_up)
        self.assertEqual(info.cascade_up.parent.pk, milestone.pk)


class ApplyCascadeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.actor = UserFactory()

    def test_apply_cascade_down_issues(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)

        apply_cascade(
            cascade_down_pks=[story.pk],
            cascade_down_status=IssueStatus.DONE,
            cascade_down_model_type="issue",
            cascade_up_pk=None,
            cascade_up_status="",
            cascade_up_model_type="",
            actor=self.actor,
        )

        story.refresh_from_db()
        self.assertEqual(story.status, IssueStatus.DONE)

    def test_apply_cascade_down_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        apply_cascade(
            cascade_down_pks=[subtask.pk],
            cascade_down_status=SubtaskStatus.DONE,
            cascade_down_model_type="subtask",
            cascade_up_pk=None,
            cascade_up_status="",
            cascade_up_model_type="",
            actor=self.actor,
        )

        subtask.refresh_from_db()
        self.assertEqual(subtask.status, SubtaskStatus.DONE)

    def test_apply_cascade_down_milestones(self):
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)

        apply_cascade(
            cascade_down_pks=[milestone.pk],
            cascade_down_status=IssueStatus.DONE,
            cascade_down_model_type="milestone",
            cascade_up_pk=None,
            cascade_up_status="",
            cascade_up_model_type="",
            actor=self.actor,
        )

        milestone.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.DONE)

    def test_apply_cascade_up_project(self):
        apply_cascade(
            cascade_down_pks=[],
            cascade_down_status="",
            cascade_down_model_type="",
            cascade_up_pk=self.project.pk,
            cascade_up_status=ProjectStatus.COMPLETED,
            cascade_up_model_type="project",
            actor=self.actor,
        )

        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.COMPLETED)

    def test_apply_cascade_up_milestone(self):
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        apply_cascade(
            cascade_down_pks=[],
            cascade_down_status="",
            cascade_down_model_type="",
            cascade_up_pk=milestone.pk,
            cascade_up_status=IssueStatus.DONE,
            cascade_up_model_type="milestone",
            actor=self.actor,
        )

        milestone.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.DONE)

    def test_apply_cascade_up_issue(self):
        epic = EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        apply_cascade(
            cascade_down_pks=[],
            cascade_down_status="",
            cascade_down_model_type="",
            cascade_up_pk=epic.pk,
            cascade_up_status=IssueStatus.DONE,
            cascade_up_model_type="issue",
            actor=self.actor,
        )

        epic.refresh_from_db()
        self.assertEqual(epic.status, IssueStatus.DONE)

    def test_apply_cascade_both_directions(self):
        epic = EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)

        apply_cascade(
            cascade_down_pks=[story.pk],
            cascade_down_status=IssueStatus.DONE,
            cascade_down_model_type="issue",
            cascade_up_pk=milestone.pk,
            cascade_up_status=IssueStatus.DONE,
            cascade_up_model_type="milestone",
            actor=self.actor,
        )

        story.refresh_from_db()
        milestone.refresh_from_db()
        self.assertEqual(story.status, IssueStatus.DONE)
        self.assertEqual(milestone.status, IssueStatus.DONE)

    def test_apply_cascade_down_mixed_milestones_and_issues(self):
        """Project cascade DOWN updates both milestones and epics."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)
        orphan_epic = EpicFactory(project=self.project, milestone=None, status=IssueStatus.DRAFT)

        apply_cascade(
            cascade_down_pks=[milestone.pk, orphan_epic.pk],
            cascade_down_status=IssueStatus.DONE,
            cascade_down_model_type="issue",
            cascade_up_pk=None,
            cascade_up_status="",
            cascade_up_model_type="",
            actor=self.actor,
        )

        milestone.refresh_from_db()
        orphan_epic.refresh_from_db()
        self.assertEqual(milestone.status, IssueStatus.DONE)
        self.assertEqual(orphan_epic.status, IssueStatus.DONE)


class DeepCascadeDownTest(TestCase):
    """Tests for deep cascade DOWN that reaches all descendants."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_project_completed_cascades_to_all_descendants(self):
        """Project COMPLETED cascades to milestones, epics, stories, and subtasks."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)
        epic = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.IN_PROGRESS)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(self.project, ProjectStatus.COMPLETED)

        self.assertIsNotNone(info.cascade_down)
        # Should have 3 groups: milestone, issue, subtask
        self.assertEqual(len(info.cascade_down.groups), 3)

        milestone_group = info.cascade_down.groups[0]
        self.assertEqual(milestone_group.model_type, "milestone")
        self.assertEqual(len(milestone_group.items), 1)
        self.assertEqual(milestone_group.items[0].pk, milestone.pk)
        self.assertEqual(milestone_group.target_status, IssueStatus.DONE)

        issue_group = info.cascade_down.groups[1]
        self.assertEqual(issue_group.model_type, "issue")
        issue_pks = {i.pk for i in issue_group.items}
        self.assertIn(epic.pk, issue_pks)
        self.assertIn(story.pk, issue_pks)
        self.assertEqual(issue_group.target_status, IssueStatus.DONE)

        subtask_group = info.cascade_down.groups[2]
        self.assertEqual(subtask_group.model_type, "subtask")
        self.assertEqual(len(subtask_group.items), 1)
        self.assertEqual(subtask_group.items[0].pk, subtask.pk)
        self.assertEqual(subtask_group.target_status, SubtaskStatus.DONE)

        # total_count includes all
        self.assertEqual(info.cascade_down.total_count, 4)

    def test_milestone_done_cascades_to_epics_and_their_descendants(self):
        """Milestone DONE cascades to its epics, their work items, and subtasks."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        epic = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.PLANNING)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(milestone, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_down)
        # Should have 2 groups: issue (epic + story), subtask
        self.assertEqual(len(info.cascade_down.groups), 2)

        issue_group = info.cascade_down.groups[0]
        self.assertEqual(issue_group.model_type, "issue")
        issue_pks = {i.pk for i in issue_group.items}
        self.assertIn(epic.pk, issue_pks)
        self.assertIn(story.pk, issue_pks)

        subtask_group = info.cascade_down.groups[1]
        self.assertEqual(subtask_group.model_type, "subtask")
        self.assertEqual(len(subtask_group.items), 1)
        self.assertEqual(subtask_group.items[0].pk, subtask.pk)

    def test_epic_done_cascades_to_work_items_and_subtasks(self):
        """Epic DONE cascades to all descendant work items and their subtasks."""
        epic = EpicFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(epic, IssueStatus.DONE)

        self.assertIsNotNone(info.cascade_down)
        # Should have 2 groups: issue (story), subtask
        self.assertEqual(len(info.cascade_down.groups), 2)

        issue_group = info.cascade_down.groups[0]
        self.assertEqual(issue_group.model_type, "issue")
        self.assertEqual(len(issue_group.items), 1)
        self.assertEqual(issue_group.items[0].pk, story.pk)

        subtask_group = info.cascade_down.groups[1]
        self.assertEqual(subtask_group.model_type, "subtask")
        self.assertEqual(len(subtask_group.items), 1)
        self.assertEqual(subtask_group.items[0].pk, subtask.pk)

    def test_deep_cascade_respects_eligibility(self):
        """Items already completed are excluded at each level."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DONE)
        epic = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.DONE)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(self.project, ProjectStatus.COMPLETED)

        self.assertIsNotNone(info.cascade_down)
        # Milestone and epic are already DONE -> not eligible for project cascade
        # But story is DRAFT -> eligible as issue
        # Subtask is TODO -> but its parent story is eligible, so subtask should be included
        all_pks = {c.pk for c in info.cascade_down.all_items}
        self.assertNotIn(milestone.pk, all_pks)
        self.assertNotIn(epic.pk, all_pks)
        self.assertIn(story.pk, all_pks)
        self.assertIn(subtask.pk, all_pks)

    def test_project_cascade_no_groups_when_all_completed(self):
        """Returns None when all descendants are already completed."""
        MilestoneFactory(project=self.project, status=IssueStatus.DONE)
        epic = EpicFactory(project=self.project, status=IssueStatus.DONE)
        StoryFactory(project=self.project, parent=epic, status=IssueStatus.DONE)

        info = check_cascade_opportunities(self.project, ProjectStatus.COMPLETED)

        self.assertIsNone(info.cascade_down)

    def test_project_archived_cascades_deeply(self):
        """Project ARCHIVED cascades to all descendants with ARCHIVED/DONE targets."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.IN_PROGRESS)
        epic = EpicFactory(project=self.project, milestone=milestone, status=IssueStatus.PLANNING)
        story = StoryFactory(project=self.project, parent=epic, status=IssueStatus.DRAFT)
        SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        info = check_cascade_opportunities(self.project, ProjectStatus.ARCHIVED)

        self.assertIsNotNone(info.cascade_down)
        self.assertEqual(len(info.cascade_down.groups), 3)

        # Milestones get ARCHIVED target
        self.assertEqual(info.cascade_down.groups[0].target_status, IssueStatus.ARCHIVED)
        # Issues get ARCHIVED target
        self.assertEqual(info.cascade_down.groups[1].target_status, IssueStatus.ARCHIVED)
        # Subtasks get DONE target (no ARCHIVED in SubtaskStatus)
        self.assertEqual(info.cascade_down.groups[2].target_status, SubtaskStatus.DONE)
