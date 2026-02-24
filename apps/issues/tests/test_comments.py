from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory, StoryFactory
from apps.projects.factories import ProjectFactory
from apps.users.factories import CustomUserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER

from django_comments_xtd.models import XtdComment


class IssueCommentsTestBase(TestCase):
    """Base test class for issue comments views."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = CustomUserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _create_comment(self, issue, user=None, text="Test comment"):
        content_type = ContentType.objects.get_for_model(issue)
        return XtdComment.objects.create(
            content_type=content_type,
            object_pk=str(issue.pk),
            site_id=1,
            user=user or self.user,
            comment=text,
        )

    def _get_comments_url(self, issue):
        return reverse(
            "issues:issue_comments",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_comment_post_url(self, issue):
        return reverse(
            "issues:issue_comment_post",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_comment_edit_url(self, issue, comment_pk):
        return reverse(
            "issues:issue_comment_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
                "comment_pk": comment_pk,
            },
        )

    def _get_comment_delete_url(self, issue, comment_pk):
        return reverse(
            "issues:issue_comment_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
                "comment_pk": comment_pk,
            },
        )


class IssueCommentsViewTest(IssueCommentsTestBase):
    """Tests for the IssueCommentsView."""

    def test_comments_view_returns_200(self):
        """Comments view returns 200 for authenticated user."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_comments_url(story))

        self.assertEqual(200, response.status_code)

    def test_comments_view_shows_existing_comments(self):
        """Comments view displays existing comments."""
        story = StoryFactory(project=self.project)
        content_type = ContentType.objects.get_for_model(story)
        XtdComment.objects.create(
            content_type=content_type,
            object_pk=str(story.pk),
            site_id=1,
            user=self.user,
            comment="Test comment",
        )

        response = self.client.get(self._get_comments_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Test comment")

    def test_comments_view_works_for_epic(self):
        """Comments view works for epics as well."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_comments_url(epic))

        self.assertEqual(200, response.status_code)

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        self.client.logout()

        response = self.client.get(self._get_comments_url(story))

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)


class IssueCommentPostViewTest(IssueCommentsTestBase):
    """Tests for the IssueCommentPostView."""

    def test_post_comment_creates_comment(self):
        """Posting a comment creates a new XtdComment."""
        story = StoryFactory(project=self.project)
        content_type = ContentType.objects.get_for_model(story)

        response = self.client.post(self._get_comment_post_url(story), {"comment": "My new comment"})

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            1,
            XtdComment.objects.filter(content_type=content_type, object_pk=str(story.pk)).count(),
        )
        comment = XtdComment.objects.get(content_type=content_type, object_pk=str(story.pk))
        self.assertEqual("My new comment", comment.comment)
        self.assertEqual(self.user, comment.user)

    def test_post_empty_comment_returns_400(self):
        """Posting an empty comment returns 400 error."""
        story = StoryFactory(project=self.project)

        response = self.client.post(self._get_comment_post_url(story), {"comment": ""})

        self.assertEqual(400, response.status_code)

    def test_post_comment_returns_updated_list(self):
        """Posting a comment returns the updated comments list."""
        story = StoryFactory(project=self.project)

        response = self.client.post(self._get_comment_post_url(story), {"comment": "Brand new comment"})

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Brand new comment")

    def test_anonymous_user_cannot_post_comment(self):
        """Anonymous user is redirected when trying to post a comment."""
        story = StoryFactory(project=self.project)
        self.client.logout()

        response = self.client.post(self._get_comment_post_url(story), {"comment": "Test"})

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)


class IssueCommentEditViewTest(IssueCommentsTestBase):
    """Tests for the IssueCommentEditView."""

    def test_owner_can_edit_comment(self):
        """Comment owner can edit their own comment."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, text="Original text")

        response = self.client.post(
            self._get_comment_edit_url(story, comment.pk),
            {"comment": "Updated text"},
        )

        self.assertEqual(200, response.status_code)
        comment.refresh_from_db()
        self.assertEqual("Updated text", comment.comment)

    def test_non_owner_gets_403(self):
        """Non-owner cannot edit another user's comment."""
        other_user = CustomUserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user, role=ROLE_MEMBER)
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, user=other_user, text="Their comment")

        response = self.client.post(
            self._get_comment_edit_url(story, comment.pk),
            {"comment": "Hijacked"},
        )

        self.assertEqual(403, response.status_code)
        comment.refresh_from_db()
        self.assertEqual("Their comment", comment.comment)

    def test_empty_text_returns_400(self):
        """Editing with empty text returns 400."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, text="Original text")

        response = self.client.post(
            self._get_comment_edit_url(story, comment.pk),
            {"comment": ""},
        )

        self.assertEqual(400, response.status_code)
        comment.refresh_from_db()
        self.assertEqual("Original text", comment.comment)

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story)
        self.client.logout()

        response = self.client.post(
            self._get_comment_edit_url(story, comment.pk),
            {"comment": "Updated"},
        )

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_edit_returns_updated_list(self):
        """Editing a comment returns the updated comments list HTML."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, text="Old text")

        response = self.client.post(
            self._get_comment_edit_url(story, comment.pk),
            {"comment": "New text"},
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "New text")
        self.assertNotContains(response, "Old text")


class IssueCommentDeleteViewTest(IssueCommentsTestBase):
    """Tests for the IssueCommentDeleteView."""

    def test_owner_can_delete_comment(self):
        """Comment owner can soft-delete their own comment."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, text="To be deleted")

        response = self.client.post(self._get_comment_delete_url(story, comment.pk))

        self.assertEqual(200, response.status_code)
        comment.refresh_from_db()
        self.assertTrue(comment.is_removed)

    def test_non_owner_gets_403(self):
        """Non-owner cannot delete another user's comment."""
        other_user = CustomUserFactory()
        MembershipFactory(workspace=self.workspace, user=other_user, role=ROLE_MEMBER)
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story, user=other_user, text="Their comment")

        response = self.client.post(self._get_comment_delete_url(story, comment.pk))

        self.assertEqual(403, response.status_code)
        comment.refresh_from_db()
        self.assertFalse(comment.is_removed)

    def test_anonymous_user_redirects_to_login(self):
        """Anonymous user is redirected to login."""
        story = StoryFactory(project=self.project)
        comment = self._create_comment(story)
        self.client.logout()

        response = self.client.post(self._get_comment_delete_url(story, comment.pk))

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_deleted_comment_not_in_list(self):
        """Deleted comment does not appear in the returned comments list."""
        story = StoryFactory(project=self.project)
        self._create_comment(story, text="Visible comment")
        to_delete = self._create_comment(story, text="Delete me")

        response = self.client.post(self._get_comment_delete_url(story, to_delete.pk))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Visible comment")
        self.assertNotContains(response, "Delete me")
