from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory, MilestoneFactory, StoryFactory, SubtaskFactory
from apps.issues.models import BaseIssue, Milestone, Subtask
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class SubtaskCascadeDeleteTest(TestCase):
    """Tests verifying subtasks are deleted via treebeard cascade when parent is deleted."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_subtask_deleted_when_parent_story_deleted(self):
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)

        story.delete()

        self.assertEqual(0, Subtask.objects.count())

    def test_multiple_subtasks_deleted_across_stories(self):
        epic = EpicFactory(project=self.project)
        story1 = StoryFactory(project=self.project, parent=epic)
        story2 = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story1)
        SubtaskFactory(parent=story2)
        SubtaskFactory(parent=story2)

        epic.delete()

        self.assertEqual(0, Subtask.objects.count())


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
        # work_item_count counts direct descendants of epics (story + subtask = 2)
        self.assertEqual(response.context["work_item_count"], 2)

    def test_milestone_delete_with_no_epics(self):
        milestone = MilestoneFactory(project=self.project)

        self.client.post(self._get_delete_url(milestone))

        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())


class IssueDeleteCascadeTest(TestCase):
    """Tests for issue deletion with subtask cascade."""

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

    def test_issue_delete_get_shows_descendant_count(self):
        """Delete confirm page shows descendant_count (includes subtasks as tree descendants)."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)

        response = self.client.get(self._get_delete_url(story))

        self.assertEqual(response.status_code, 200)
        # Subtasks are now tree descendants counted in descendant_count
        self.assertEqual(response.context["descendant_count"], 2)


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
        # work_item_count = non-epic BaseIssues (story + subtask = 2)
        self.assertEqual(response.context["work_item_count"], 2)


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
