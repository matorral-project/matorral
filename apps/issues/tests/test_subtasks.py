from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import (
    BaseIssueSubtaskFactory,
    BugFactory,
    ChoreFactory,
    EpicFactory,
    StoryFactory,
)
from apps.issues.models import IssueStatus
from apps.issues.views.subtasks import MAX_SUBTASKS_PER_PARENT
from apps.projects.factories import ProjectFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class SubtaskTestBase(TestCase):
    """Base test class for subtask tests."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_subtasks_url(self, issue):
        return reverse(
            "issues:issue_subtasks",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_subtask_add_url(self, issue):
        return reverse(
            "issues:issue_subtask_add",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_subtask_edit_url(self, issue, subtask):
        return reverse(
            "issues:issue_subtask_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
                "subtask_pk": subtask.pk,
            },
        )

    def _get_subtask_delete_url(self, issue, subtask):
        return reverse(
            "issues:issue_subtask_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
                "subtask_pk": subtask.pk,
            },
        )

    def _get_subtask_toggle_url(self, issue, subtask):
        return reverse(
            "issues:issue_subtask_toggle",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
                "subtask_pk": subtask.pk,
            },
        )


class SubtaskCreationTest(TestCase):
    """Tests for creating subtasks as BaseIssue children."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_subtask_can_be_created_as_child_of_story(self):
        """Subtask (BaseIssue) can be created as child of Story."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Test subtask")

        self.assertEqual("Test subtask", subtask.title)
        self.assertEqual(IssueStatus.READY, subtask.status)
        self.assertEqual(story, subtask.get_parent())

    def test_subtask_can_be_created_as_child_of_bug(self):
        """Subtask (BaseIssue) can be created as child of Bug."""
        bug = BugFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=bug, title="Bug subtask")

        self.assertEqual(bug, subtask.get_parent())

    def test_subtask_can_be_created_as_child_of_chore(self):
        """Subtask (BaseIssue) can be created as child of Chore."""
        chore = ChoreFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=chore, title="Chore subtask")

        self.assertEqual(chore, subtask.get_parent())

    def test_subtask_inherits_project_from_parent(self):
        """Subtask inherits project from parent work item."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Test")

        self.assertEqual(self.project, subtask.project)

    def test_subtask_gets_key_assigned(self):
        """Subtask gets auto-generated key."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Test")

        self.assertTrue(subtask.key)
        self.assertTrue(subtask.key.startswith(self.project.key))


class SubtaskTreeTest(TestCase):
    """Tests for subtask tree structure."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_get_children_returns_subtasks(self):
        """get_children() returns subtasks of a work item."""
        story = StoryFactory(project=self.project)
        subtask1 = BaseIssueSubtaskFactory(parent=story, title="Subtask 1")
        subtask2 = BaseIssueSubtaskFactory(parent=story, title="Subtask 2")

        children = list(story.get_children())

        self.assertEqual(2, len(children))
        self.assertIn(subtask1, children)
        self.assertIn(subtask2, children)

    def test_subtasks_ordered_by_key(self):
        """Subtasks are ordered by key."""
        story = StoryFactory(project=self.project)
        subtask1 = BaseIssueSubtaskFactory(parent=story, title="A")
        subtask2 = BaseIssueSubtaskFactory(parent=story, title="B")
        subtask3 = BaseIssueSubtaskFactory(parent=story, title="C")

        children = list(story.get_children().order_by("key"))

        # Should be ordered by key (which is auto-generated based on creation order)
        self.assertEqual(subtask1, children[0])
        self.assertEqual(subtask2, children[1])
        self.assertEqual(subtask3, children[2])


class SubtaskListViewTest(SubtaskTestBase):
    """Tests for SubtaskListView."""

    def test_list_view_returns_200(self):
        """Subtask list view returns 200 for authenticated user."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_subtasks_url(story))

        self.assertEqual(200, response.status_code)

    def test_list_view_shows_subtasks(self):
        """Subtask list view displays existing subtasks."""
        story = StoryFactory(project=self.project)
        BaseIssueSubtaskFactory(parent=story, title="Test subtask 1")
        BaseIssueSubtaskFactory(parent=story, title="Test subtask 2")

        response = self.client.get(self._get_subtasks_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Test subtask 1")
        self.assertContains(response, "Test subtask 2")

    def test_list_view_shows_multiple_subtasks(self):
        """Subtask list view displays multiple subtasks."""
        story = StoryFactory(project=self.project)
        BaseIssueSubtaskFactory(parent=story, title="First subtask")
        BaseIssueSubtaskFactory(parent=story, title="Second subtask")

        response = self.client.get(self._get_subtasks_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "First subtask")
        self.assertContains(response, "Second subtask")

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        self.client.logout()

        response = self.client.get(self._get_subtasks_url(story))

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)


class SubtaskCreateViewTest(SubtaskTestBase):
    """Tests for SubtaskCreateView."""

    def test_create_subtask_success(self):
        """Creating a subtask works."""
        # Create story with an epic parent to ensure proper tree structure
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)

        response = self.client.post(self._get_subtask_add_url(story), {"title": "New subtask"})

        self.assertEqual(200, response.status_code)
        # Refresh story to get updated tree state
        story.refresh_from_db()
        self.assertEqual(1, story.get_children().count())
        subtask = story.get_children().first()
        self.assertEqual("New subtask", subtask.title)

    def test_create_subtask_returns_updated_list(self):
        """Creating a subtask returns the updated list."""
        story = StoryFactory(project=self.project)

        response = self.client.post(self._get_subtask_add_url(story), {"title": "New subtask"})

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "New subtask")

    def test_create_subtask_at_limit_rejected(self):
        """Creating a subtask when at the limit is rejected."""
        story = StoryFactory(project=self.project)

        # Create max subtasks
        for i in range(MAX_SUBTASKS_PER_PARENT):
            BaseIssueSubtaskFactory(parent=story, title=f"Subtask {i}")

        response = self.client.post(self._get_subtask_add_url(story), {"title": "One more"})

        self.assertEqual(400, response.status_code)
        self.assertEqual(MAX_SUBTASKS_PER_PARENT, story.get_children().count())

    def test_created_subtask_has_ready_status(self):
        """New subtasks are created with READY status."""
        story = StoryFactory(project=self.project)

        self.client.post(self._get_subtask_add_url(story), {"title": "New subtask"})

        # Refresh to see the new child (treebeard materialized path)
        story.refresh_from_db()
        subtask = story.get_children().first()
        self.assertEqual(IssueStatus.READY, subtask.status)


class SubtaskInlineEditViewTest(SubtaskTestBase):
    """Tests for SubtaskInlineEditView."""

    def test_get_shows_edit_form(self):
        """GET shows the edit form."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Original title")

        response = self.client.get(self._get_subtask_edit_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Original title")
        self.assertContains(response, "fa-check")  # Save button

    def test_get_with_cancel_returns_display_mode(self):
        """GET with cancel parameter returns display mode."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Original title")

        response = self.client.get(self._get_subtask_edit_url(story, subtask) + "?cancel=1")

        self.assertEqual(200, response.status_code)

    def test_post_updates_subtask(self):
        """POST updates the subtask."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Original title", status=IssueStatus.READY)

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated title", "status": "in_progress"},
        )

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual("Updated title", subtask.title)
        self.assertEqual(IssueStatus.IN_PROGRESS, subtask.status)

    def test_post_returns_display_mode(self):
        """POST returns the updated row in display mode."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Original")

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated", "status": "done"},
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Updated")


class SubtaskDeleteViewTest(SubtaskTestBase):
    """Tests for SubtaskDeleteView."""

    def test_delete_subtask(self):
        """Deleting a subtask removes it."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="To delete")

        response = self.client.post(self._get_subtask_delete_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, story.get_children().count())

    def test_delete_returns_updated_list(self):
        """Deleting a subtask returns the updated list."""
        story = StoryFactory(project=self.project)
        BaseIssueSubtaskFactory(parent=story, title="Keep this one")
        subtask_to_delete = BaseIssueSubtaskFactory(parent=story, title="Remove me please")

        response = self.client.post(self._get_subtask_delete_url(story, subtask_to_delete))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Keep this one")
        self.assertNotContains(response, "Remove me please")


class SubtaskStatusToggleViewTest(SubtaskTestBase):
    """Tests for SubtaskStatusToggleView."""

    def test_toggle_ready_to_in_progress(self):
        """Toggling a ready subtask marks it as in_progress."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, status=IssueStatus.READY)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, subtask.status)

    def test_toggle_in_progress_to_done(self):
        """Toggling an in_progress subtask marks it as done."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.DONE, subtask.status)

    def test_toggle_done_to_ready(self):
        """Toggling a done subtask marks it as ready (cycles back)."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, status=IssueStatus.DONE)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.READY, subtask.status)

    def test_toggle_wont_do_to_ready(self):
        """Toggling a wont_do subtask marks it as ready."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, status=IssueStatus.WONT_DO)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.READY, subtask.status)

    def test_toggle_returns_updated_row(self):
        """Toggling returns the updated row."""
        story = StoryFactory(project=self.project)
        subtask = BaseIssueSubtaskFactory(parent=story, title="Toggle me", status=IssueStatus.READY)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Toggle me")
        self.assertContains(response, "fa-spinner")  # In Progress state icon
