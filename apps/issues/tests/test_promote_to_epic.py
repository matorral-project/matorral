from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, MilestoneFactory, StoryFactory, SubtaskFactory
from apps.issues.models import Epic, IssueStatus, Story, Subtask, SubtaskStatus
from apps.issues.services import PromotionError, promote_to_epic
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN

from auditlog.models import LogEntry
from django_comments_xtd.models import XtdComment


class PromoteToEpicServiceTest(TestCase):
    """Tests for the promote_to_epic service function."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_promote_story_to_epic(self):
        """Promoting a Story to Epic creates an Epic with the same key and title."""
        story = StoryFactory(
            project=self.project,
            title="Test Story",
            description="Test description",
            priority="high",
            status=IssueStatus.IN_PROGRESS,
        )
        original_key = story.key
        original_pk = story.pk

        epic = promote_to_epic(story)

        self.assertIsInstance(epic, Epic)
        self.assertEqual(original_pk, epic.pk)
        self.assertEqual(original_key, epic.key)
        self.assertEqual("Test Story", epic.title)
        self.assertEqual("Test description", epic.description)
        self.assertEqual("high", epic.priority)
        self.assertEqual(IssueStatus.IN_PROGRESS, epic.status)

    def test_promote_bug_to_epic(self):
        """Promoting a Bug to Epic works and loses severity."""
        bug = BugFactory(
            project=self.project,
            title="Test Bug",
            priority="critical",
            severity="blocker",
        )
        original_key = bug.key

        epic = promote_to_epic(bug)

        self.assertIsInstance(epic, Epic)
        self.assertEqual(original_key, epic.key)
        self.assertEqual("Test Bug", epic.title)
        self.assertEqual("critical", epic.priority)
        self.assertFalse(hasattr(epic, "severity"))

    def test_promote_chore_to_epic(self):
        """Promoting a Chore to Epic works correctly."""
        chore = ChoreFactory(project=self.project, title="Test Chore")

        epic = promote_to_epic(chore)

        self.assertIsInstance(epic, Epic)
        self.assertEqual("Test Chore", epic.title)

    def test_promote_epic_raises_error(self):
        """Attempting to promote an Epic raises an error."""
        epic = EpicFactory(project=self.project)

        with self.assertRaises(PromotionError):
            promote_to_epic(epic)

    def test_promote_sets_milestone(self):
        """Promoting with a milestone links the Epic to the milestone."""
        story = StoryFactory(project=self.project)
        milestone = MilestoneFactory(project=self.project)

        epic = promote_to_epic(story, milestone=milestone)

        self.assertEqual(milestone, epic.milestone)

    def test_promote_moves_to_root_when_has_parent(self):
        """Promoting an item with a parent Epic moves it to root level."""
        parent_epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=parent_epic)

        # Verify story is a child
        self.assertEqual(parent_epic, story.get_parent())

        epic = promote_to_epic(story)

        # Refresh from DB
        epic.refresh_from_db()
        # Epic should now be at root level (no parent)
        self.assertIsNone(epic.get_parent())
        self.assertEqual(1, epic.depth)

    def test_promote_inherits_parent_milestone(self):
        """Promoting an item inherits the parent epic's milestone when no milestone is specified."""
        milestone = MilestoneFactory(project=self.project)
        parent_epic = EpicFactory(project=self.project, milestone=milestone)
        story = StoryFactory(project=self.project, parent=parent_epic)

        epic = promote_to_epic(story)

        epic.refresh_from_db()
        self.assertEqual(milestone, epic.milestone)

    def test_promote_inherits_parent_milestone_with_no_milestone(self):
        """Promoting an item under a parent epic with no milestone results in no milestone."""
        parent_epic = EpicFactory(project=self.project, milestone=None)
        story = StoryFactory(project=self.project, parent=parent_epic)

        epic = promote_to_epic(story)

        epic.refresh_from_db()
        self.assertIsNone(epic.milestone)

    def test_promote_explicit_milestone_overrides_parent(self):
        """An explicitly provided milestone takes precedence over the parent's milestone."""
        parent_milestone = MilestoneFactory(project=self.project, title="Parent MS")
        explicit_milestone = MilestoneFactory(project=self.project, title="Explicit MS")
        parent_epic = EpicFactory(project=self.project, milestone=parent_milestone)
        story = StoryFactory(project=self.project, parent=parent_epic)

        epic = promote_to_epic(story, milestone=explicit_milestone)

        epic.refresh_from_db()
        self.assertEqual(explicit_milestone, epic.milestone)

    def test_promote_preserves_comments(self):
        """Promoting preserves comments with updated ContentType."""
        story = StoryFactory(project=self.project)
        content_type = ContentType.objects.get_for_model(Story)
        comment = XtdComment.objects.create(
            content_type=content_type,
            object_pk=str(story.pk),
            site_id=1,
            comment="Test comment",
        )

        promote_to_epic(story)

        # Fetch updated comment
        updated_comment = XtdComment.objects.get(pk=comment.pk)
        self.assertEqual("Test comment", updated_comment.comment)
        self.assertEqual(ContentType.objects.get_for_model(Epic), updated_comment.content_type)

    def test_promote_preserves_history(self):
        """Promoting preserves audit log entries with updated ContentType."""
        story = StoryFactory(project=self.project)
        story_ct = ContentType.objects.get_for_model(Story)

        # Count existing log entries for this story
        existing_count = LogEntry.objects.filter(content_type=story_ct, object_id=story.pk).count()

        # Create a pre-existing audit log entry
        LogEntry.objects.create(
            content_type=story_ct,
            object_id=story.pk,
            object_pk=str(story.pk),
            object_repr=str(story),
            action=LogEntry.Action.UPDATE,
            changes={"title": ["Old Title", "Test Title"]},
        )

        promote_to_epic(story)

        # Fetch audit log entries for the issue
        epic_ct = ContentType.objects.get_for_model(Epic)
        log_entries = LogEntry.objects.filter(content_type=epic_ct, object_id=story.pk)
        # Should have existing entries + our custom entry + the promotion entry
        self.assertEqual(existing_count + 2, log_entries.count())

    def test_promote_creates_audit_log_entry(self):
        """Promoting creates an audit log entry for the type change."""
        story = StoryFactory(project=self.project)
        initial_log_count = LogEntry.objects.count()

        promote_to_epic(story)

        # Should have created one new log entry
        self.assertEqual(initial_log_count + 1, LogEntry.objects.count())
        log_entry = LogEntry.objects.order_by("-timestamp").first()
        self.assertEqual(ContentType.objects.get_for_model(Epic), log_entry.content_type)
        self.assertEqual(story.pk, log_entry.object_id)
        self.assertIn("type", log_entry.changes)
        self.assertEqual(["Story", "Epic"], log_entry.changes["type"])

    def test_promote_converts_subtasks_to_stories(self):
        """Promoting converts subtasks to Stories as children of the new Epic."""
        story = StoryFactory(project=self.project, priority="high")
        SubtaskFactory(parent=story, title="Subtask 1", status=SubtaskStatus.TODO)
        SubtaskFactory(parent=story, title="Subtask 2", status=SubtaskStatus.IN_PROGRESS)
        SubtaskFactory(parent=story, title="Subtask 3", status=SubtaskStatus.DONE)

        epic = promote_to_epic(story, convert_subtasks=True)

        # Original subtasks should be deleted
        self.assertEqual(0, Subtask.objects.count())

        # New stories should exist as children of the Epic
        children = list(epic.get_children())
        self.assertEqual(3, len(children))

        # Verify each child Story
        child_titles = {c.title for c in children}
        self.assertEqual({"Subtask 1", "Subtask 2", "Subtask 3"}, child_titles)

        # Verify status mapping
        for child in children:
            self.assertIsInstance(child, Story)
            self.assertEqual("high", child.priority)  # Inherits parent's priority
            if child.title == "Subtask 1":
                self.assertEqual(IssueStatus.DRAFT, child.status)
            elif child.title == "Subtask 2":
                self.assertEqual(IssueStatus.IN_PROGRESS, child.status)
            elif child.title == "Subtask 3":
                self.assertEqual(IssueStatus.DONE, child.status)

    def test_promote_with_wont_do_subtask(self):
        """Promoting maps WONT_DO subtask status correctly."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Cancelled task", status=SubtaskStatus.WONT_DO)

        epic = promote_to_epic(story, convert_subtasks=True)

        child = epic.get_children().first()
        self.assertEqual(IssueStatus.WONT_DO, child.status)

    def test_promote_without_subtask_conversion_deletes_subtasks(self):
        """Promoting with convert_subtasks=False deletes subtasks."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Subtask 1")
        SubtaskFactory(parent=story, title="Subtask 2")

        epic = promote_to_epic(story, convert_subtasks=False)

        # Subtasks should be deleted
        self.assertEqual(0, Subtask.objects.count())
        # No children should exist
        self.assertEqual(0, epic.get_children().count())

    def test_promote_preserves_tree_children(self):
        """Promoting preserves existing tree children (they become Epic's children)."""
        story = StoryFactory(project=self.project)
        child_story = StoryFactory(project=self.project, parent=story, title="Child Story")

        epic = promote_to_epic(story)

        # Child should still exist as a child of the Epic
        epic.refresh_from_db()
        children = list(epic.get_children())
        self.assertEqual(1, len(children))
        self.assertEqual(child_story.pk, children[0].pk)
        self.assertEqual("Child Story", children[0].title)


class IssuePromoteToEpicViewTest(TestCase):
    """Tests for the IssuePromoteToEpicView."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_promote_url(self, issue):
        return reverse(
            "issues:issue_promote",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_returns_modal_content(self):
        """GET request returns the promotion modal content."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Promote to Epic")
        self.assertContains(response, story.key)

    def test_get_shows_subtask_count(self):
        """Modal content shows the subtask count when subtasks exist."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Subtask 1")
        SubtaskFactory(parent=story, title="Subtask 2")

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "2 subtasks")
        self.assertContains(response, "convert_subtasks")

    def test_get_shows_data_loss_warnings(self):
        """Modal content shows appropriate data loss warnings."""
        sprint = SprintFactory(workspace=self.workspace)
        story = StoryFactory(project=self.project, estimated_points=5, sprint=sprint)

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Estimated points will be lost")
        self.assertContains(response, "Sprint assignment will be removed")

    def test_get_shows_severity_warning_for_bug(self):
        """Modal content shows severity warning for bugs."""
        bug = BugFactory(project=self.project, severity="major")

        response = self.client.get(self._get_promote_url(bug))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Severity will be lost")

    def test_get_preselects_parent_milestone(self):
        """Modal preselects the parent epic's milestone in the form."""
        milestone = MilestoneFactory(project=self.project)
        parent_epic = EpicFactory(project=self.project, milestone=milestone)
        story = StoryFactory(project=self.project, parent=parent_epic)

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(200, response.status_code)
        # The milestone option should be selected
        self.assertContains(response, f'value="{milestone.pk}" selected')

    def test_get_epic_shows_error(self):
        """GET request for an Epic shows an error message."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_promote_url(epic), follow=True)

        self.assertEqual(200, response.status_code)

    def test_post_promotes_story_to_epic(self):
        """POST request successfully promotes Story to Epic."""
        story = StoryFactory(project=self.project, title="Test Story")
        original_pk = story.pk

        response = self.client.post(self._get_promote_url(story), {})

        # Should redirect to the promoted epic's detail page
        self.assertEqual(302, response.status_code)

        # Verify the promotion
        epic = Epic.objects.get(pk=original_pk)
        self.assertEqual("Test Story", epic.title)

    def test_post_with_milestone(self):
        """POST request with milestone sets the milestone on the Epic."""
        story = StoryFactory(project=self.project)
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(
            self._get_promote_url(story),
            {"milestone": milestone.pk},
        )

        self.assertEqual(302, response.status_code)

        epic = Epic.objects.get(pk=story.pk)
        self.assertEqual(milestone, epic.milestone)

    def test_post_with_subtask_conversion(self):
        """POST request converts subtasks when checkbox is checked."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Subtask 1")

        response = self.client.post(
            self._get_promote_url(story),
            {"convert_subtasks": "on"},
        )

        self.assertEqual(302, response.status_code)

        epic = Epic.objects.get(pk=story.pk)
        children = list(epic.get_children())
        self.assertEqual(1, len(children))
        self.assertEqual("Subtask 1", children[0].title)

    def test_post_without_subtask_conversion(self):
        """POST request without checkbox deletes subtasks."""
        story = StoryFactory(project=self.project)
        SubtaskFactory(parent=story, title="Subtask 1")

        response = self.client.post(
            self._get_promote_url(story),
            {},  # No convert_subtasks checkbox
        )

        self.assertEqual(302, response.status_code)

        epic = Epic.objects.get(pk=story.pk)
        self.assertEqual(0, epic.get_children().count())
        self.assertEqual(0, Subtask.objects.count())

    def test_post_epic_returns_error(self):
        """POST request for an Epic returns an error."""
        epic = EpicFactory(project=self.project)

        response = self.client.post(
            self._get_promote_url(epic),
            {},
            follow=True,
        )

        self.assertEqual(200, response.status_code)

    def test_htmx_post_returns_redirect_header(self):
        """HTMX POST request returns HX-Redirect header."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_promote_url(story),
            {},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        self.assertIn("HX-Redirect", response.headers)

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        self.client.logout()

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_non_team_member_denied_access(self):
        """Non-workspace member cannot access the promote view."""
        story = StoryFactory(project=self.project)
        other_user = UserFactory()
        self.client.force_login(other_user)

        response = self.client.get(self._get_promote_url(story))

        self.assertEqual(404, response.status_code)
