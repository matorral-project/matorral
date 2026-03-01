"""Tests for apps/issues/views/bulk.py."""

from django.contrib.messages import get_messages
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, EpicFactory, StoryFactory, SubtaskFactory
from apps.issues.models import Bug, IssuePriority, IssueStatus, Story
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import SprintStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN

from auditlog.models import LogEntry


class BulkActionTestBase(TestCase):
    """Base test class for bulk action view tests."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _url(self, name):
        return reverse(name, kwargs={"workspace_slug": self.workspace.slug})

    def _post(self, name, data, htmx=False):
        url = self._url(name)
        kwargs = {}
        if htmx:
            kwargs["HTTP_HX_REQUEST"] = "true"
        return self.client.post(url, data, **kwargs)


class TestBulkActionNoIssuesSelected(BulkActionTestBase):
    """Test 1: Bulk action with no issues selected re-renders without redirect."""

    def test_empty_selection_adds_warning_and_rerenders(self):
        """POSTing with no issues selected adds a warning and re-renders (HTMX, no redirect)."""
        response = self._post("workspace_issues_bulk_delete", {}, htmx=True)

        self.assertEqual(200, response.status_code)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("No issues selected" in str(m) for m in messages_list),
            f"Expected 'No issues selected' warning in messages, got: {[str(m) for m in messages_list]}",
        )


class TestBulkDeletePreviewCascadeCounts(BulkActionTestBase):
    """Test 2: Bulk delete preview modal shows correct descendant and subtask counts."""

    def test_preview_context_includes_descendant_and_subtask_counts(self):
        """Preview modal counts the selected epic, its story descendant, and story's subtasks."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        SubtaskFactory(parent=story)
        SubtaskFactory(parent=story)

        response = self._post(
            "workspace_issues_bulk_delete_preview",
            {"issues": epic.key},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.context["selected_count"])
        # Story is the sole descendant of the epic
        self.assertEqual(1, response.context["descendant_count"])
        # Both subtasks belong to the story (a descendant of the selected epic)
        self.assertEqual(2, response.context["subtask_count"])


class TestBulkStatusInvalidValue(BulkActionTestBase):
    """Test 3: Bulk status update rejects invalid status without touching the DB."""

    def test_invalid_status_value_returns_error_and_leaves_db_unchanged(self):
        """An unrecognised status string adds an error and does not update any issue."""
        story = StoryFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self._post(
            "workspace_issues_bulk_status",
            {"issues": story.key, "status": "NOT_A_VALID_STATUS"},
            htmx=True,
        )

        # View re-renders (200), not a redirect
        self.assertEqual(200, response.status_code)

        # DB row is unchanged
        story.refresh_from_db()
        self.assertEqual(IssueStatus.DRAFT, story.status)

        # Error message is present
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Invalid status" in str(m) for m in messages_list),
            f"Expected 'Invalid status' error in messages, got: {[str(m) for m in messages_list]}",
        )


class TestBulkPriorityPolymorphicUpdate(BulkActionTestBase):
    """Test 4: Bulk priority update writes to each concrete table and creates audit logs."""

    def test_priority_updated_on_story_and_bug_with_one_audit_log_each(self):
        """Priority is updated on both Story and Bug concrete tables; one LogEntry per issue."""
        story = StoryFactory(project=self.project, priority=IssuePriority.LOW)
        bug = BugFactory(project=self.project, priority=IssuePriority.LOW)
        initial_log_count = LogEntry.objects.count()

        self._post(
            "workspace_issues_bulk_priority",
            {"issues": [story.key, bug.key], "priority": IssuePriority.HIGH},
        )

        story.refresh_from_db()
        bug.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, story.priority)
        self.assertEqual(IssuePriority.HIGH, bug.priority)

        # One audit log entry per issue (old != new, so both are logged)
        self.assertEqual(initial_log_count + 2, LogEntry.objects.count())


class TestBulkAddToSprintKeyNotFound(BulkActionTestBase):
    """Test 5: Bulk add-to-sprint with a sprint key that does not exist."""

    def test_nonexistent_sprint_key_adds_error_and_leaves_sprint_unset(self):
        """A sprint key that matches no sprint in the workspace adds an error and sets no FK."""
        story = StoryFactory(project=self.project)

        response = self._post(
            "workspace_issues_bulk_add_to_sprint",
            {"issues": story.key, "sprint": "NONEXISTENT-9999"},
            htmx=True,
        )

        self.assertEqual(200, response.status_code)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Invalid sprint" in str(m) for m in messages_list),
            f"Expected 'Invalid sprint' error in messages, got: {[str(m) for m in messages_list]}",
        )
        story.refresh_from_db()
        self.assertIsNone(story.sprint)


class TestBulkAddToSprintCompletedStatus(BulkActionTestBase):
    """Test 6: Bulk add-to-sprint rejects sprints in COMPLETED status."""

    def test_completed_sprint_is_rejected_and_sprint_fk_stays_null(self):
        """A completed sprint is not a valid target; validation blocks the action."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        story = StoryFactory(project=self.project)

        response = self._post(
            "workspace_issues_bulk_add_to_sprint",
            {"issues": story.key, "sprint": sprint.key},
            htmx=True,
        )

        self.assertEqual(200, response.status_code)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("Invalid sprint" in str(m) for m in messages_list),
            f"Expected 'Invalid sprint' error in messages, got: {[str(m) for m in messages_list]}",
        )
        story.refresh_from_db()
        self.assertIsNone(story.sprint)


class TestBulkRemoveFromSprintSuccess(BulkActionTestBase):
    """Test 7: Bulk remove-from-sprint clears sprint FK and creates audit logs."""

    def test_sprint_fk_cleared_and_audit_log_created_per_issue(self):
        """Sprint is set to None on each issue and one LogEntry is created for each."""
        sprint = SprintFactory(workspace=self.workspace)
        story = StoryFactory(project=self.project)
        bug = BugFactory(project=self.project)
        # Assign both issues to the sprint directly (factory doesn't expose sprint)
        Story.objects.filter(pk=story.pk).update(sprint=sprint)
        Bug.objects.filter(pk=bug.pk).update(sprint=sprint)
        initial_log_count = LogEntry.objects.count()

        self._post(
            "workspace_issues_bulk_remove_from_sprint",
            {"issues": [story.key, bug.key]},
        )

        story.refresh_from_db()
        bug.refresh_from_db()
        self.assertIsNone(story.sprint)
        self.assertIsNone(bug.sprint)

        # One audit log per issue that had its sprint cleared
        self.assertEqual(initial_log_count + 2, LogEntry.objects.count())


class TestBulkAssigneeUnassign(BulkActionTestBase):
    """Test 8: Bulk assignee — unassigning clears the assignee and shows the right message."""

    def test_empty_assignee_clears_field_and_success_message_says_unassigned(self):
        """Posting assignee='' sets assignee=None on the issue and surfaces an 'unassigned' message."""
        assignee = UserFactory()
        MembershipFactory(workspace=self.workspace, user=assignee, role=ROLE_ADMIN)
        story = StoryFactory(project=self.project, assignee=assignee)

        response = self._post(
            "workspace_issues_bulk_assignee",
            {"issues": story.key, "assignee": ""},
            htmx=True,
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertIsNone(story.assignee)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(
            any("unassigned" in str(m).lower() for m in messages_list),
            f"Expected 'unassigned' success message, got: {[str(m) for m in messages_list]}",
        )


class TestRenderResponseSprintEmbed(BulkActionTestBase):
    """Test 9: render_response with embed=sprint uses the sprint partial template."""

    def test_sprint_embed_renders_sprint_partial_with_sprint_in_context(self):
        """HTMX bulk action with embed=sprint renders the sprint issues embed template."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)
        story = StoryFactory(project=self.project)
        Story.objects.filter(pk=story.pk).update(sprint=sprint)

        response = self._post(
            "workspace_issues_bulk_priority",
            {
                "issues": story.key,
                "priority": IssuePriority.HIGH,
                "embed": "sprint",
                "sprint_filter": sprint.key,
            },
            htmx=True,
        )

        self.assertEqual(200, response.status_code)
        # django-template-partials registers the fragment as "embed-content",
        # not the parent file name, when rendering "issues/issues_embed.html#embed-content".
        self.assertTemplateUsed(response, "embed-content")
        self.assertIn("sprint", response.context)
        self.assertEqual(sprint.pk, response.context["sprint"].pk)
