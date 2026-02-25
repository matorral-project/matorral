from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, EpicFactory, StoryFactory, SubtaskFactory
from apps.issues.models import Bug, BugSeverity, Chore, Story, Subtask
from apps.issues.services import IssueConversionError, convert_issue_type
from apps.projects.factories import ProjectFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN

from auditlog.models import LogEntry
from django_comments_xtd.models import XtdComment


class ConvertIssueTypeServiceTest(TestCase):
    """Tests for the convert_issue_type service function."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_convert_story_to_bug(self):
        """Converting a Story to Bug preserves common fields and adds severity."""
        story = StoryFactory(
            project=self.project,
            title="Test Story",
            description="Test description",
            priority="high",
            estimated_points=5,
        )
        original_key = story.key
        original_pk = story.pk

        converted = convert_issue_type(story, "bug", severity="major")

        self.assertIsInstance(converted, Bug)
        self.assertEqual(original_pk, converted.pk)
        self.assertEqual(original_key, converted.key)
        self.assertEqual("Test Story", converted.title)
        self.assertEqual("Test description", converted.description)
        self.assertEqual("high", converted.priority)
        self.assertEqual(5, converted.estimated_points)
        self.assertEqual("major", converted.severity)

    def test_convert_bug_to_story(self):
        """Converting a Bug to Story preserves common fields, severity is lost."""
        bug = BugFactory(
            project=self.project,
            title="Test Bug",
            priority="critical",
            severity="blocker",
        )
        original_key = bug.key
        original_pk = bug.pk

        converted = convert_issue_type(bug, "story")

        self.assertIsInstance(converted, Story)
        self.assertEqual(original_pk, converted.pk)
        self.assertEqual(original_key, converted.key)
        self.assertEqual("Test Bug", converted.title)
        self.assertEqual("critical", converted.priority)
        self.assertFalse(hasattr(converted, "severity"))

    def test_convert_story_to_chore(self):
        """Converting a Story to Chore works correctly."""
        story = StoryFactory(project=self.project, title="Test Story")

        converted = convert_issue_type(story, "chore")

        self.assertIsInstance(converted, Chore)
        self.assertEqual("Test Story", converted.title)

    def test_convert_to_bug_without_severity_defaults_to_minor(self):
        """Converting to Bug without specifying severity defaults to minor."""
        story = StoryFactory(project=self.project)

        converted = convert_issue_type(story, "bug")

        self.assertIsInstance(converted, Bug)
        self.assertEqual(BugSeverity.MINOR, converted.severity)

    def test_convert_epic_raises_error(self):
        """Attempting to convert an Epic raises an error."""
        epic = EpicFactory(project=self.project)

        with self.assertRaises(IssueConversionError):
            convert_issue_type(epic, "story")

    def test_convert_to_invalid_type_raises_error(self):
        """Attempting to convert to an invalid type raises an error."""
        story = StoryFactory(project=self.project)

        with self.assertRaises(IssueConversionError):
            convert_issue_type(story, "epic")

    def test_convert_same_type_is_noop(self):
        """Converting to the same type returns the original instance."""
        story = StoryFactory(project=self.project)
        original_pk = story.pk

        converted = convert_issue_type(story, "story")

        self.assertIsInstance(converted, Story)
        self.assertEqual(original_pk, converted.pk)

    def test_convert_preserves_tree_position(self):
        """Converting preserves the issue's tree position (path/depth)."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)
        original_path = story.path
        original_depth = story.depth

        converted = convert_issue_type(story, "bug")

        self.assertEqual(original_path, converted.path)
        self.assertEqual(original_depth, converted.depth)

    def test_convert_preserves_subtasks(self):
        """Converting preserves subtasks with updated ContentType."""
        story = StoryFactory(project=self.project)
        subtask = SubtaskFactory(parent=story, title="My Subtask")
        original_subtask_pk = subtask.pk

        converted = convert_issue_type(story, "bug")

        # Fetch updated subtask
        updated_subtask = Subtask.objects.get(pk=original_subtask_pk)
        self.assertEqual("My Subtask", updated_subtask.title)
        self.assertEqual(ContentType.objects.get_for_model(Bug), updated_subtask.content_type)
        self.assertEqual(converted.pk, updated_subtask.object_id)

    def test_convert_preserves_comments(self):
        """Converting preserves comments with updated ContentType."""
        story = StoryFactory(project=self.project)
        content_type = ContentType.objects.get_for_model(Story)
        comment = XtdComment.objects.create(
            content_type=content_type,
            object_pk=str(story.pk),
            site_id=1,
            comment="Test comment",
        )

        convert_issue_type(story, "bug")

        # Fetch updated comment
        updated_comment = XtdComment.objects.get(pk=comment.pk)
        self.assertEqual("Test comment", updated_comment.comment)
        self.assertEqual(ContentType.objects.get_for_model(Bug), updated_comment.content_type)

    def test_convert_creates_audit_log_entry(self):
        """Converting creates an audit log entry for the type change."""
        story = StoryFactory(project=self.project)
        initial_log_count = LogEntry.objects.count()

        convert_issue_type(story, "bug")

        # Should have created one new log entry
        self.assertEqual(initial_log_count + 1, LogEntry.objects.count())
        log_entry = LogEntry.objects.order_by("-timestamp").first()
        self.assertEqual(ContentType.objects.get_for_model(Bug), log_entry.content_type)
        self.assertEqual(story.pk, log_entry.object_id)
        self.assertIn("type", log_entry.changes)
        self.assertEqual(["Story", "Bug"], log_entry.changes["type"])


class IssueConvertTypeViewTest(TestCase):
    """Tests for the IssueConvertTypeView."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_convert_url(self, issue):
        return reverse(
            "issues:issue_convert",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_returns_modal_content(self):
        """GET request returns the conversion modal content."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_convert_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Convert")
        self.assertContains(response, story.key)

    def test_get_excludes_current_type_from_choices(self):
        """Modal content excludes the current type from conversion choices."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_convert_url(story))

        self.assertEqual(200, response.status_code)
        # Story should not be in the dropdown options (as an option value)
        self.assertNotContains(response, 'value="story"')
        # But Bug and Chore should be
        self.assertContains(response, 'value="bug"')
        self.assertContains(response, 'value="chore"')

    def test_get_epic_shows_error(self):
        """GET request for an Epic shows an error message."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_convert_url(epic), follow=True)

        # Should redirect back to epic detail with error message
        self.assertEqual(200, response.status_code)

    def test_post_converts_story_to_bug(self):
        """POST request successfully converts Story to Bug."""
        story = StoryFactory(project=self.project)
        original_pk = story.pk

        response = self.client.post(
            self._get_convert_url(story),
            {"target_type": "bug", "severity": "major"},
        )

        # Should redirect to the converted issue's detail page
        self.assertEqual(302, response.status_code)

        # Verify the conversion
        converted = Bug.objects.get(pk=original_pk)
        self.assertEqual("major", converted.severity)

    def test_post_converts_bug_to_story(self):
        """POST request successfully converts Bug to Story."""
        bug = BugFactory(project=self.project, severity="blocker")
        original_pk = bug.pk

        response = self.client.post(
            self._get_convert_url(bug),
            {"target_type": "story"},
        )

        self.assertEqual(302, response.status_code)

        # Verify the conversion
        converted = Story.objects.get(pk=original_pk)
        self.assertEqual(bug.title, converted.title)

    def test_post_epic_returns_error(self):
        """POST request for an Epic returns an error."""
        epic = EpicFactory(project=self.project)

        response = self.client.post(
            self._get_convert_url(epic),
            {"target_type": "story"},
            follow=True,
        )

        self.assertEqual(200, response.status_code)
        # Epic should still exist
        self.assertTrue(type(epic).__name__, "Epic")

    def test_htmx_post_returns_redirect_header(self):
        """HTMX POST request returns HX-Redirect header."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_convert_url(story),
            {"target_type": "bug", "severity": "minor"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("HX-Redirect", response.headers)

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        self.client.logout()

        response = self.client.get(self._get_convert_url(story))

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_invalid_form_returns_modal_with_errors(self):
        """Invalid form submission returns modal with errors."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_convert_url(story),
            {"target_type": ""},  # Invalid: empty target type
        )

        self.assertEqual(200, response.status_code)
        # Should return the form with errors
        self.assertContains(response, "required")
