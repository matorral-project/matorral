from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, StoryFactory, SubtaskFactory
from apps.issues.models import Subtask, SubtaskStatus
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


class SubtaskModelTest(TestCase):
    """Tests for the Subtask model."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_subtask_creation(self):
        """Subtask can be created with a parent issue."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Test subtask")

        self.assertEqual("Test subtask", subtask.title)
        self.assertEqual(SubtaskStatus.TODO, subtask.status)
        self.assertEqual(story.pk, subtask.object_id)

    def test_subtask_parent_is_content_type(self):
        """Subtask stores parent via GenericForeignKey."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story)

        content_type = ContentType.objects.get_for_model(story)
        self.assertEqual(content_type, subtask.content_type)
        self.assertEqual(story.pk, subtask.object_id)

    def test_subtask_str(self):
        """Subtask __str__ returns title."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="My subtask")

        self.assertEqual("My subtask", str(subtask))

    def test_subtask_title_stripped_on_save(self):
        """Subtask title is stripped on save."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="  Whitespace title  ")

        self.assertEqual("Whitespace title", subtask.title)

    def test_subtask_works_with_different_issue_types(self):
        """Subtasks can be created for Story, Bug, and Chore types."""
        story = StoryFactory(project=self.project)
        bug = BugFactory(project=self.project)
        chore = ChoreFactory(project=self.project)

        for parent in [story, bug, chore]:
            subtask = SubtaskFactory(parent=parent, title=f"Subtask for {parent.__class__.__name__}")
            self.assertEqual(parent.pk, subtask.object_id)


class SubtaskManagerTest(TestCase):
    """Tests for SubtaskManager."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_for_parent_filters_correctly(self):
        """for_parent returns only subtasks for the given parent."""
        story1 = StoryFactory(project=self.project)
        story2 = StoryFactory(project=self.project)

        subtask1 = SubtaskFactory(parent=story1, title="Subtask 1")
        subtask2 = SubtaskFactory(parent=story1, title="Subtask 2")
        SubtaskFactory(parent=story2, title="Subtask 3")

        subtasks = Subtask.objects.for_parent(story1)

        self.assertEqual(2, subtasks.count())
        self.assertIn(subtask1, subtasks)
        self.assertIn(subtask2, subtasks)


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
        SubtaskFactory(parent=story, title="Test subtask 1")
        SubtaskFactory(parent=story, title="Test subtask 2")

        response = self.client.get(self._get_subtasks_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Test subtask 1")
        self.assertContains(response, "Test subtask 2")

    def test_list_view_shows_multiple_subtasks(self):
        """Subtask list view displays multiple subtasks."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="First subtask")
        SubtaskFactory(parent=story, title="Second subtask")

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
        story = StoryFactory(project=self.project)

        response = self.client.post(self._get_subtask_add_url(story), {"title": "New subtask"})

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, Subtask.objects.for_parent(story).count())
        subtask = Subtask.objects.for_parent(story).first()
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
            SubtaskFactory(parent=story, title=f"Subtask {i}")

        response = self.client.post(self._get_subtask_add_url(story), {"title": "One more"})

        self.assertEqual(400, response.status_code)
        self.assertEqual(MAX_SUBTASKS_PER_PARENT, Subtask.objects.for_parent(story).count())

    def test_create_subtask_position_auto_increments(self):
        """New subtasks get position at the end."""
        story = StoryFactory(project=self.project)

        self.client.post(self._get_subtask_add_url(story), {"title": "First"})
        self.client.post(self._get_subtask_add_url(story), {"title": "Second"})
        self.client.post(self._get_subtask_add_url(story), {"title": "Third"})

        subtasks = list(Subtask.objects.for_parent(story).order_by("position"))
        self.assertEqual(0, subtasks[0].position)
        self.assertEqual(1, subtasks[1].position)
        self.assertEqual(2, subtasks[2].position)


class SubtaskInlineEditViewTest(SubtaskTestBase):
    """Tests for SubtaskInlineEditView."""

    def test_get_shows_edit_form(self):
        """GET shows the edit form."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original title")

        response = self.client.get(self._get_subtask_edit_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Original title")
        self.assertContains(response, "fa-check")  # Save button

    def test_get_with_cancel_returns_display_mode(self):
        """GET with cancel parameter returns display mode."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original title")

        response = self.client.get(self._get_subtask_edit_url(story, subtask) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        # Should be in display mode (no input fields for editing, just text)

    def test_post_updates_subtask(self):
        """POST updates the subtask."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original title", status=SubtaskStatus.TODO)

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated title", "status": SubtaskStatus.IN_PROGRESS},
        )

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual("Updated title", subtask.title)
        self.assertEqual(SubtaskStatus.IN_PROGRESS, subtask.status)

    def test_post_returns_display_mode(self):
        """POST returns the updated row in display mode."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original")

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated", "status": SubtaskStatus.DONE},
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Updated")


class SubtaskDeleteViewTest(SubtaskTestBase):
    """Tests for SubtaskDeleteView."""

    def test_delete_subtask(self):
        """Deleting a subtask removes it."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="To delete")

        response = self.client.post(self._get_subtask_delete_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertEqual(0, Subtask.objects.for_parent(story).count())

    def test_delete_returns_updated_list(self):
        """Deleting a subtask returns the updated list."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Keep this one")
        subtask_to_delete = SubtaskFactory(parent=story, title="Remove me please")

        response = self.client.post(self._get_subtask_delete_url(story, subtask_to_delete))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Keep this one")
        self.assertNotContains(response, "Remove me please")


class SubtaskStatusToggleViewTest(SubtaskTestBase):
    """Tests for SubtaskStatusToggleView."""

    def test_toggle_todo_to_in_progress(self):
        """Toggling a todo subtask marks it as in_progress."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.TODO)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(SubtaskStatus.IN_PROGRESS, subtask.status)

    def test_toggle_in_progress_to_done(self):
        """Toggling an in_progress subtask marks it as done."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.IN_PROGRESS)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(SubtaskStatus.DONE, subtask.status)

    def test_toggle_done_to_todo(self):
        """Toggling a done subtask marks it as todo."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.DONE)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(SubtaskStatus.TODO, subtask.status)

    def test_toggle_wont_do_to_todo(self):
        """Toggling a wont_do subtask marks it as todo."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=SubtaskStatus.WONT_DO)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(SubtaskStatus.TODO, subtask.status)

    def test_toggle_returns_updated_row(self):
        """Toggling returns the updated row."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Toggle me", status=SubtaskStatus.TODO)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Toggle me")
        self.assertContains(response, "fa-spinner")  # In Progress state icon
