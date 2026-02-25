from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory, MilestoneFactory, StoryFactory, SubtaskFactory
from apps.issues.helpers import count_subtasks_for_issue_ids, delete_subtasks_for_issue_ids
from apps.issues.models import BaseIssue, Milestone, Subtask
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class SubtaskCleanupHelpersTest(TestCase):
    """Tests for subtask cleanup utility functions."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_count_subtasks_for_empty_ids(self):
        self.assertEqual(count_subtasks_for_issue_ids([]), 0)

    def test_count_subtasks_for_issue_ids(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)
        self.assertEqual(count_subtasks_for_issue_ids([story.pk]), 2)

    def test_delete_subtasks_for_issue_ids(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)
        deleted = delete_subtasks_for_issue_ids([story.pk])
        self.assertEqual(deleted, 2)
        self.assertEqual(Subtask.objects.filter(object_id=story.pk).count(), 0)

    def test_delete_subtasks_for_empty_ids(self):
        self.assertEqual(delete_subtasks_for_issue_ids([]), 0)

    def test_count_subtasks_across_multiple_issues(self):
        epic = EpicFactory(project=self.project)
        story1 = StoryFactory(project=self.project, parent=epic)
        story2 = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story1)
        SubtaskFactory(parent=story2)
        SubtaskFactory(parent=story2)
        self.assertEqual(count_subtasks_for_issue_ids([story1.pk, story2.pk]), 3)


class MilestoneCascadeDeleteTest(TestCase):
    """Tests for milestone cascade deletion (epics + descendants + subtasks)."""

    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.project = ProjectFactory(workspace=self.workspace)
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_ADMIN)
        self.client = Client()
        self.client.force_login(self.user)

    def _get_delete_url(self, milestone):
        return reverse(
            "milestones:milestone_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_milestone_delete_cascades_to_epics(self):
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone)
        epic_pk = epic.pk

        self.client.post(self._get_delete_url(milestone))

        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())
        self.assertFalse(BaseIssue.objects.filter(pk=epic_pk).exists())

    def test_milestone_delete_cascades_to_epic_descendants(self):
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone)
        story = StoryFactory(project=self.project, parent=epic)
        story_pk = story.pk

        self.client.post(self._get_delete_url(milestone))

        self.assertFalse(BaseIssue.objects.filter(pk=story_pk).exists())

    def test_milestone_delete_cleans_up_subtasks(self):
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story)
        subtask_pk = subtask.pk

        self.client.post(self._get_delete_url(milestone))

        self.assertFalse(Subtask.objects.filter(pk=subtask_pk).exists())

    def test_milestone_delete_get_shows_cascade_counts(self):
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)

        response = self.client.get(self._get_delete_url(milestone))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["epic_count"], 1)
        self.assertEqual(response.context["work_item_count"], 1)
        self.assertEqual(response.context["subtask_count"], 1)

    def test_milestone_delete_with_no_epics(self):
        milestone = MilestoneFactory(project=self.project)

        self.client.post(self._get_delete_url(milestone))

        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())


class IssueDeleteCascadeTest(TestCase):
    """Tests for issue deletion with subtask cleanup."""

    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.project = ProjectFactory(workspace=self.workspace)
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_ADMIN)
        self.client = Client()
        self.client.force_login(self.user)

    def _get_delete_url(self, issue):
        return reverse(
            "issues:issue_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_issue_delete_cleans_up_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story)
        subtask_pk = subtask.pk

        self.client.post(self._get_delete_url(story))

        self.assertFalse(Subtask.objects.filter(pk=subtask_pk).exists())

    def test_epic_delete_cleans_up_descendant_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)

        self.client.post(self._get_delete_url(epic))

        self.assertEqual(Subtask.objects.count(), 0)

    def test_issue_delete_get_shows_subtask_count(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)

        response = self.client.get(self._get_delete_url(story))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["subtask_count"], 2)


class ProjectDeleteCascadeTest(TestCase):
    """Tests for project deletion with subtask cleanup."""

    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.project = ProjectFactory(workspace=self.workspace)
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_ADMIN)
        self.client = Client()
        self.client.force_login(self.user)

    def _get_delete_url(self):
        return reverse(
            "projects:project_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": self.project.key,
            },
        )

    def test_project_delete_cleans_up_subtasks(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story)
        subtask_pk = subtask.pk

        self.client.post(self._get_delete_url())

        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(Subtask.objects.filter(pk=subtask_pk).exists())

    def test_project_delete_get_shows_cascade_counts(self):
        milestone = MilestoneFactory(project=self.project)  # noqa: F841
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)

        response = self.client.get(self._get_delete_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["milestone_count"], 1)
        self.assertEqual(response.context["epic_count"], 1)
        self.assertEqual(response.context["work_item_count"], 1)
        self.assertEqual(response.context["subtask_count"], 1)


class SprintDeleteTest(TestCase):
    """Tests for sprint deletion (no cascade, just unlink)."""

    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.project = ProjectFactory(workspace=self.workspace)
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_ADMIN)
        self.client = Client()
        self.client.force_login(self.user)

    def _get_delete_url(self, sprint):
        return reverse(
            "sprints:sprint_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def test_sprint_delete_unlinks_issues(self):
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=sprint)

        self.client.post(self._get_delete_url(sprint))

        self.assertFalse(Sprint.objects.filter(pk=sprint.pk).exists())
        # Story should still exist, just unlinked from sprint
        story.refresh_from_db()
        self.assertIsNone(story.sprint)

    def test_sprint_delete_get_shows_item_count(self):
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=sprint)

        response = self.client.get(self._get_delete_url(sprint))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["item_count"], 1)
