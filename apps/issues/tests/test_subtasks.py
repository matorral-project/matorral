from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, StoryFactory, SubtaskFactory
from apps.issues.models import IssueStatus, Subtask
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

    def _get_subtask_clone_url(self, issue, subtask):
        return reverse(
            "issues:issue_subtask_clone",
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
        self.assertEqual(IssueStatus.DRAFT, subtask.status)
        self.assertEqual(story.pk, subtask.get_parent().pk)

    def test_subtask_is_tree_child_of_parent(self):
        """Subtask is stored as a treebeard child of its parent."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story)

        children_pks = {c.pk for c in story.get_children()}
        self.assertIn(subtask.pk, children_pks)

    def test_subtask_str(self):
        """Subtask __str__ includes key and title."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="My subtask")

        self.assertIn("My subtask", str(subtask))
        self.assertIn(subtask.key, str(subtask))

    def test_subtask_gets_issue_key(self):
        """Subtask gets a project-scoped key on creation."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story)

        self.assertIsNotNone(subtask.key)
        self.assertTrue(subtask.key.startswith(self.project.key))

    def test_subtask_works_with_different_issue_types(self):
        """Subtasks can be created for Story, Bug, and Chore types."""
        story = StoryFactory(project=self.project)
        bug = BugFactory(project=self.project)
        chore = ChoreFactory(project=self.project)

        for parent in [story, bug, chore]:
            subtask = SubtaskFactory(parent=parent, title=f"Subtask for {parent.__class__.__name__}")
            self.assertEqual(parent.pk, subtask.get_parent().pk)

    def test_subtask_deleted_with_parent(self):
        """Subtask is cascade-deleted when its parent work item is deleted."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story)
        subtask_pk = subtask.pk

        story.delete()

        self.assertFalse(Subtask.objects.filter(pk=subtask_pk).exists())


class SubtaskValidationTest(TestCase):
    """Tests for Subtask._validate_parent_type()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_validate_parent_type_passes_for_story(self):
        """Valid: subtask under a Story."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story)

        # Should not raise
        subtask._validate_parent_type()

    def test_validate_parent_type_passes_for_bug(self):
        """Valid: subtask under a Bug."""
        bug = BugFactory(project=self.project)
        subtask = SubtaskFactory(parent=bug)

        subtask._validate_parent_type()

    def test_validate_parent_type_passes_for_chore(self):
        """Valid: subtask under a Chore."""
        chore = ChoreFactory(project=self.project)
        subtask = SubtaskFactory(parent=chore)

        subtask._validate_parent_type()

    def test_validate_parent_type_rejects_epic_parent(self):
        """Invalid: subtask cannot be a direct child of an Epic."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        subtask = SubtaskFactory(parent=story)

        # Move subtask to be a direct child of the epic
        subtask.move(epic, pos="last-child")
        subtask.refresh_from_db()

        with self.assertRaises(ValidationError):
            subtask._validate_parent_type()


class SubtaskTreeTest(TestCase):
    """Tests for Subtask tree relationships."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_get_children_filters_correctly(self):
        """get_children returns only subtasks for the given parent."""
        story1 = StoryFactory(project=self.project)
        story2 = StoryFactory(project=self.project)

        subtask1 = SubtaskFactory(parent=story1, title="Subtask 1")
        subtask2 = SubtaskFactory(parent=story1, title="Subtask 2")
        SubtaskFactory(parent=story2, title="Subtask 3")

        subtasks = story1.get_children().instance_of(Subtask)

        self.assertEqual(2, subtasks.count())
        subtask_pks = {s.pk for s in subtasks}
        self.assertIn(subtask1.pk, subtask_pks)
        self.assertIn(subtask2.pk, subtask_pks)


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

        # Check the story now has a subtask
        story.refresh_from_db()
        subtask_qs = story.get_children().instance_of(Subtask)
        self.assertEqual(1, subtask_qs.count())

        # Check the subtask was properly created
        subtask = subtask_qs.get()
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

        for i in range(MAX_SUBTASKS_PER_PARENT):
            SubtaskFactory(parent=story, title=f"Subtask {i}")

        response = self.client.post(self._get_subtask_add_url(story), {"title": "One more"})

        self.assertEqual(400, response.status_code)
        self.assertEqual(MAX_SUBTASKS_PER_PARENT, story.get_children().instance_of(Subtask).count())

    def test_create_subtask_ordered_by_treebeard_path(self):
        """New subtasks are ordered by treebeard path (insertion order)."""
        story = StoryFactory(project=self.project)

        self.client.post(self._get_subtask_add_url(story), {"title": "First"})
        self.client.post(self._get_subtask_add_url(story), {"title": "Second"})
        self.client.post(self._get_subtask_add_url(story), {"title": "Third"})

        # we need to refresh the story since we're using treebeard
        story.refresh_from_db()

        subtasks_qs = story.get_children().instance_of(Subtask)
        self.assertEqual(3, subtasks_qs.count())

        titles = list(subtasks_qs.values_list("title", flat=True))
        self.assertListEqual(["First", "Second", "Third"], titles)


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

    def test_post_updates_subtask(self):
        """POST updates the subtask."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original title", status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated title", "status": IssueStatus.IN_PROGRESS},
        )

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual("Updated title", subtask.title)
        self.assertEqual(IssueStatus.IN_PROGRESS, subtask.status)

    def test_post_returns_display_mode(self):
        """POST returns the updated row in display mode."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original")

        response = self.client.post(
            self._get_subtask_edit_url(story, subtask),
            {"title": "Updated", "status": IssueStatus.DONE},
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
        self.assertEqual(0, story.get_children().instance_of(Subtask).count())

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

    def test_toggle_draft_to_in_progress(self):
        """Toggling a draft subtask marks it as in_progress."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=IssueStatus.DRAFT)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, subtask.status)

    def test_toggle_in_progress_to_done(self):
        """Toggling an in_progress subtask marks it as done."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=IssueStatus.IN_PROGRESS)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.DONE, subtask.status)

    def test_toggle_done_to_draft(self):
        """Toggling a done subtask marks it as draft."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=IssueStatus.DONE)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.DRAFT, subtask.status)

    def test_toggle_wont_do_to_draft(self):
        """Toggling a wont_do subtask marks it as draft."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=IssueStatus.WONT_DO)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        subtask.refresh_from_db()
        self.assertEqual(IssueStatus.DRAFT, subtask.status)

    def test_toggle_returns_updated_row(self):
        """Toggling returns the updated row."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Toggle me", status=IssueStatus.DRAFT)

        response = self.client.post(self._get_subtask_toggle_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Toggle me")
        self.assertContains(response, "In Progress")  # Status badge text


class SubtaskListViewFormTest(SubtaskTestBase):
    """Tests for SubtaskListView with ?form=1 (modal creation form)."""

    def test_form_endpoint_returns_200(self):
        """GET with ?form=1 returns the creation form."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_subtasks_url(story) + "?form=1")

        self.assertEqual(200, response.status_code)

    def test_form_endpoint_contains_title_input(self):
        """GET with ?form=1 returns a form with a title input."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_subtasks_url(story) + "?form=1")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, 'name="title"')


class SubtaskCloneViewTest(SubtaskTestBase):
    """Tests for SubtaskCloneView."""

    def test_clone_subtask(self):
        """Cloning a subtask creates a new subtask."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original subtask")

        response = self.client.post(self._get_subtask_clone_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, story.get_children().instance_of(Subtask).count())

    def test_clone_adds_copy_suffix(self):
        """Cloned subtask title has '(Copy)' suffix."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original subtask")

        self.client.post(self._get_subtask_clone_url(story, subtask))

        story.refresh_from_db()
        titles = list(story.get_children().instance_of(Subtask).values_list("title", flat=True))
        self.assertIn("Original subtask (Copy)", titles)

    def test_clone_generates_unique_key(self):
        """Cloned subtask has a different key from the original."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="Original subtask")

        self.client.post(self._get_subtask_clone_url(story, subtask))

        story.refresh_from_db()
        keys = list(story.get_children().instance_of(Subtask).values_list("key", flat=True))
        self.assertEqual(2, len(set(keys)))

    def test_clone_preserves_status(self):
        """Cloned subtask has the same status as the original."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, status=IssueStatus.IN_PROGRESS)

        self.client.post(self._get_subtask_clone_url(story, subtask))

        story.refresh_from_db()
        cloned = story.get_children().instance_of(Subtask).exclude(pk=subtask.pk).get()
        self.assertEqual(IssueStatus.IN_PROGRESS, cloned.status)

    def test_clone_returns_updated_list(self):
        """Cloning returns the updated subtasks list."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="My subtask")

        response = self.client.post(self._get_subtask_clone_url(story, subtask))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "My subtask")
        self.assertContains(response, "My subtask (Copy)")

    def test_clone_at_limit_rejected(self):
        """Cloning when at the subtask limit returns 400."""
        story = StoryFactory(project=self.project)
        subtasks = [SubtaskFactory(parent=story, title=f"Subtask {i}") for i in range(MAX_SUBTASKS_PER_PARENT)]

        response = self.client.post(self._get_subtask_clone_url(story, subtasks[0]))

        self.assertEqual(400, response.status_code)
        self.assertEqual(MAX_SUBTASKS_PER_PARENT, story.get_children().instance_of(Subtask).count())
