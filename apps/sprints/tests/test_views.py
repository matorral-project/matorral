from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, StoryFactory
from apps.issues.models import IssueStatus
from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import Sprint, SprintStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class SprintViewTestBase(TestCase):
    """Base test class for sprint views."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        cls.other_user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

        # Create a second workspace for isolation tests
        cls.other_workspace = WorkspaceFactory()

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_list_url(self):
        return reverse(
            "sprints:sprint_list",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def _get_detail_url(self, sprint):
        return reverse(
            "sprints:sprint_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_create_url(self):
        return reverse(
            "sprints:sprint_create",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def _get_update_url(self, sprint):
        return reverse(
            "sprints:sprint_update",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_delete_url(self, sprint):
        return reverse(
            "sprints:sprint_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_start_url(self, sprint):
        return reverse(
            "sprints:sprint_start",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_complete_url(self, sprint):
        return reverse(
            "sprints:sprint_complete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_archive_url(self, sprint):
        return reverse(
            "sprints:sprint_archive",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_issues_embed_url(self, sprint):
        return reverse(
            "sprints:sprint_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_add_issues_url(self, sprint):
        return reverse(
            "sprints:sprint_add_issues",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def _get_remove_issue_url(self, sprint, issue_key):
        return reverse(
            "sprints:sprint_remove_issue",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
                "issue_key": issue_key,
            },
        )

    def _get_issue_add_to_sprint_url(self, issue_key):
        return reverse(
            "sprints:issue_add_to_sprint",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "issue_key": issue_key,
            },
        )

    def _get_issue_add_to_sprint_confirm_url(self, issue_key):
        return reverse(
            "sprints:issue_add_to_sprint_confirm",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "issue_key": issue_key,
            },
        )


class SprintListViewAccessControlTest(SprintViewTestBase):
    """Tests for sprint list view access control."""

    def test_list_requires_login(self):
        """List view redirects to login for anonymous users."""
        self.client.logout()

        response = self.client.get(self._get_list_url())

        self.assertEqual(302, response.status_code)
        self.assertIn("/login/", response.url)

    def test_list_requires_workspace_membership(self):
        """List view returns 404 for non-workspace members."""
        self.client.force_login(self.other_user)

        response = self.client.get(self._get_list_url())

        self.assertEqual(404, response.status_code)


class SprintListViewTest(SprintViewTestBase):
    """Tests for the sprint list view."""

    def test_list_view_returns_200(self):
        """List view returns 200 for authenticated workspace member."""
        response = self.client.get(self._get_list_url())

        self.assertEqual(200, response.status_code)

    def test_list_shows_workspace_sprints(self):
        """List view shows sprints from the workspace."""
        sprint = SprintFactory(workspace=self.workspace, name="Sprint Alpha")

        response = self.client.get(self._get_list_url())

        self.assertContains(response, "Sprint Alpha")
        self.assertContains(response, sprint.key)

    def test_list_does_not_show_other_workspace_sprints(self):
        """List view does not show sprints from other workspaces."""
        SprintFactory(workspace=self.workspace, name="My Sprint")
        SprintFactory(workspace=self.other_workspace, name="Other Sprint")

        response = self.client.get(self._get_list_url())

        self.assertContains(response, "My Sprint")
        self.assertNotContains(response, "Other Sprint")

    def test_list_search_by_name(self):
        """List view can search sprints by name."""
        SprintFactory(workspace=self.workspace, name="Feature Sprint")
        SprintFactory(workspace=self.workspace, name="Bug Fix Sprint")

        response = self.client.get(self._get_list_url() + "?search=Feature")

        self.assertContains(response, "Feature Sprint")
        self.assertNotContains(response, "Bug Fix Sprint")

    def test_list_filter_by_status(self):
        """List view can filter by status."""
        SprintFactory(
            workspace=self.workspace,
            name="Planning Sprint",
            status=SprintStatus.PLANNING,
        )
        SprintFactory(
            workspace=self.workspace,
            name="Completed Sprint",
            status=SprintStatus.COMPLETED,
        )

        response = self.client.get(self._get_list_url() + "?status=planning")

        self.assertContains(response, "Planning Sprint")
        self.assertNotContains(response, "Completed Sprint")

    def test_list_filter_by_owner(self):
        """List view can filter by owner."""
        SprintFactory(workspace=self.workspace, name="My Sprint", owner=self.user)
        SprintFactory(workspace=self.workspace, name="Other Sprint", owner=None)

        response = self.client.get(self._get_list_url() + f"?owner={self.user.pk}")

        self.assertContains(response, "My Sprint")
        self.assertNotContains(response, "Other Sprint")

    def test_list_filter_by_unassigned_owner(self):
        """List view can filter by unassigned owner."""
        SprintFactory(workspace=self.workspace, name="My Sprint", owner=self.user)
        SprintFactory(workspace=self.workspace, name="Unassigned Sprint", owner=None)

        response = self.client.get(self._get_list_url() + "?owner=unassigned")

        self.assertContains(response, "Unassigned Sprint")
        self.assertNotContains(response, "My Sprint")


class SprintListViewProgressTest(SprintViewTestBase):
    """Tests for sprint list view progress computation."""

    def test_sprint_with_work_items_has_progress(self):
        """Sprint with work items in various statuses has progress populated."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.DONE,
            estimated_points=5,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.IN_PROGRESS,
            estimated_points=3,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.DRAFT,
            estimated_points=2,
        )

        response = self.client.get(self._get_list_url())

        sprints = response.context["sprints"]
        self.assertEqual(1, len(sprints))
        progress = sprints[0].progress
        self.assertIsNotNone(progress)
        self.assertEqual(10, progress["total_weight"])
        self.assertEqual(5, progress["done_weight"])
        self.assertEqual(3, progress["in_progress_weight"])
        self.assertEqual(2, progress["todo_weight"])

    def test_sprint_without_work_items_has_no_progress(self):
        """Sprint with no work items has progress set to None."""
        SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_list_url())

        sprints = response.context["sprints"]
        self.assertEqual(1, len(sprints))
        self.assertIsNone(sprints[0].progress)

    def test_progress_includes_all_work_item_types(self):
        """Progress includes Story, Bug, and Chore types."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.DONE,
            estimated_points=2,
        )
        BugFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.DONE,
            estimated_points=3,
        )
        ChoreFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.IN_PROGRESS,
            estimated_points=4,
        )

        response = self.client.get(self._get_list_url())

        sprints = response.context["sprints"]
        progress = sprints[0].progress
        self.assertIsNotNone(progress)
        self.assertEqual(9, progress["total_weight"])
        self.assertEqual(5, progress["done_weight"])  # Story(2) + Bug(3)
        self.assertEqual(4, progress["in_progress_weight"])  # Chore(4)
        self.assertEqual(0, progress["todo_weight"])


class SprintDetailViewTest(SprintViewTestBase):
    """Tests for the sprint detail view."""

    def test_detail_view_returns_200(self):
        """Detail view returns 200 for existing sprint."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_url(sprint))

        self.assertEqual(200, response.status_code)

    def test_detail_view_shows_sprint_info(self):
        """Detail view displays sprint information."""
        sprint = SprintFactory(workspace=self.workspace, name="Sprint 1", goal="Complete feature X")

        response = self.client.get(self._get_detail_url(sprint))

        self.assertContains(response, "Sprint 1")
        self.assertContains(response, "Complete feature X")
        self.assertContains(response, sprint.key)

    def test_detail_shows_progress(self):
        """Detail view shows progress widget."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_url(sprint))

        self.assertEqual(200, response.status_code)
        self.assertIn("progress", response.context)

    def test_detail_404_for_other_workspace(self):
        """Detail view returns 404 for sprint from another workspace."""
        sprint = SprintFactory(workspace=self.other_workspace)

        response = self.client.get(
            reverse(
                "sprints:sprint_detail",
                kwargs={
                    "workspace_slug": self.workspace.slug,
                    "key": sprint.key,
                },
            )
        )

        self.assertEqual(404, response.status_code)

    def test_detail_404_for_nonexistent(self):
        """Detail view returns 404 for nonexistent sprint."""
        response = self.client.get(
            reverse(
                "sprints:sprint_detail",
                kwargs={
                    "workspace_slug": self.workspace.slug,
                    "key": "NONEXISTENT",
                },
            )
        )

        self.assertEqual(404, response.status_code)


class SprintCreateViewTest(SprintViewTestBase):
    """Tests for the sprint create view."""

    def test_create_view_returns_200(self):
        """Create view returns 200."""
        response = self.client.get(self._get_create_url())

        self.assertEqual(200, response.status_code)

    def test_create_view_pre_populates_dates_from_completed_sprint(self):
        """Create view pre-populates dates based on latest completed sprint."""
        # Create a completed sprint
        start_date = timezone.now().date() - timedelta(weeks=2)
        end_date = start_date + timedelta(weeks=1)
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=start_date,
            end_date=end_date,
        )

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertEqual(end_date, form.initial["start_date"])
        self.assertEqual(end_date + timedelta(days=7), form.initial["end_date"])

    def test_create_view_uses_latest_completed_sprint_dates(self):
        """Create view uses the latest completed sprint for date calculation."""
        # Create two completed sprints with different end dates
        old_end_date = timezone.now().date() - timedelta(weeks=2)
        new_end_date = timezone.now().date() - timedelta(weeks=1)
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=old_end_date - timedelta(weeks=1),
            end_date=old_end_date,
        )
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.COMPLETED,
            start_date=old_end_date,
            end_date=new_end_date,
        )

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        # Should use the latest (new_end_date), not the older one
        self.assertEqual(new_end_date, form.initial["start_date"])
        self.assertEqual(new_end_date + timedelta(days=7), form.initial["end_date"])

    def test_create_view_no_dates_without_completed_sprint(self):
        """Create view does not pre-populate dates if no completed sprint exists."""
        # Create a planning sprint (not completed)
        SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        self.assertNotIn("start_date", form.initial)
        self.assertNotIn("end_date", form.initial)

    def test_create_view_ignores_other_workspace_completed_sprints(self):
        """Create view only considers completed sprints from the current workspace."""
        # Create a completed sprint in another workspace
        other_end_date = timezone.now().date() - timedelta(weeks=1)
        SprintFactory(
            workspace=self.other_workspace,
            status=SprintStatus.COMPLETED,
            start_date=other_end_date - timedelta(weeks=1),
            end_date=other_end_date,
        )

        response = self.client.get(self._get_create_url())

        form = response.context["form"]
        # Should not have dates since there's no completed sprint in this workspace
        self.assertNotIn("start_date", form.initial)
        self.assertNotIn("end_date", form.initial)

    def test_create_sprint(self):
        """Can create a sprint via POST."""
        start_date = timezone.now().date()
        end_date = start_date + timedelta(weeks=2)

        response = self.client.post(
            self._get_create_url(),
            {
                "name": "New Sprint",
                "goal": "Sprint goal",
                "status": SprintStatus.PLANNING,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "capacity": 20,
            },
        )

        self.assertEqual(302, response.status_code)
        self.assertTrue(Sprint.objects.filter(name="New Sprint").exists())
        sprint = Sprint.objects.get(name="New Sprint")
        self.assertEqual(self.workspace, sprint.workspace)
        self.assertTrue(sprint.key.startswith("SPRINT-"))

    def test_create_validates_date_range(self):
        """Create validates end date is after start date."""
        start_date = timezone.now().date()
        end_date = start_date - timedelta(days=1)  # Invalid: end before start

        response = self.client.post(
            self._get_create_url(),
            {
                "name": "Invalid Sprint",
                "status": SprintStatus.PLANNING,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)  # Form re-displayed with errors
        self.assertFalse(Sprint.objects.filter(name="Invalid Sprint").exists())

    def test_create_validates_duration_minimum(self):
        """Create validates minimum duration of 1 week."""
        start_date = timezone.now().date()
        end_date = start_date + timedelta(days=3)  # Invalid: less than 1 week

        response = self.client.post(
            self._get_create_url(),
            {
                "name": "Short Sprint",
                "status": SprintStatus.PLANNING,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertFalse(Sprint.objects.filter(name="Short Sprint").exists())

    def test_create_validates_duration_maximum(self):
        """Create validates maximum duration of 8 weeks."""
        start_date = timezone.now().date()
        end_date = start_date + timedelta(weeks=10)  # Invalid: more than 8 weeks

        response = self.client.post(
            self._get_create_url(),
            {
                "name": "Long Sprint",
                "status": SprintStatus.PLANNING,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertFalse(Sprint.objects.filter(name="Long Sprint").exists())


class SprintUpdateViewTest(SprintViewTestBase):
    """Tests for the sprint update view."""

    def test_update_view_returns_200(self):
        """Update view returns 200."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_update_url(sprint))

        self.assertEqual(200, response.status_code)

    def test_update_sprint(self):
        """Can update a sprint via POST."""
        sprint = SprintFactory(workspace=self.workspace, name="Original Name")
        end_date = sprint.start_date + timedelta(weeks=2)

        response = self.client.post(
            self._get_update_url(sprint),
            {
                "name": "Updated Name",
                "goal": "Updated goal",
                "status": SprintStatus.PLANNING,
                "start_date": sprint.start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual("Updated Name", sprint.name)
        self.assertEqual("Updated goal", sprint.goal)


class SprintDeleteViewTest(SprintViewTestBase):
    """Tests for the sprint delete view."""

    def test_delete_view_returns_200(self):
        """Delete view returns 200."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_delete_url(sprint))

        self.assertEqual(200, response.status_code)

    def test_delete_sprint(self):
        """Can delete a sprint via POST."""
        sprint = SprintFactory(workspace=self.workspace)
        sprint_pk = sprint.pk

        response = self.client.post(self._get_delete_url(sprint))

        self.assertEqual(302, response.status_code)
        self.assertFalse(Sprint.objects.filter(pk=sprint_pk).exists())

    def test_delete_shows_item_count(self):
        """Delete view shows count of items in sprint."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=sprint)
        StoryFactory(project=self.project, parent=epic, sprint=sprint)

        response = self.client.get(self._get_delete_url(sprint))

        self.assertIn("item_count", response.context)
        self.assertEqual(2, response.context["item_count"])


class SprintStartViewTest(SprintViewTestBase):
    """Tests for the sprint start action view."""

    def test_start_sprint(self):
        """Can start a planning sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(self._get_start_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ACTIVE, sprint.status)

    def test_start_fails_when_another_active(self):
        """Cannot start sprint when another is already active."""
        SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(self._get_start_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.PLANNING, sprint.status)  # Still planning

    def test_start_fails_for_non_planning_sprint(self):
        """Cannot start a sprint that is not in planning status."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)

        response = self.client.post(self._get_start_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.COMPLETED, sprint.status)

    def test_start_captures_committed_points(self):
        """Starting a sprint captures committed points."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=sprint, estimated_points=5)
        StoryFactory(project=self.project, parent=epic, sprint=sprint, estimated_points=3)

        self.client.post(self._get_start_url(sprint))

        sprint.refresh_from_db()
        self.assertEqual(8, sprint.committed_points)


class SprintCompleteViewTest(SprintViewTestBase):
    """Tests for the sprint complete action view."""

    def test_complete_sprint(self):
        """Can complete an active sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)

        response = self.client.post(self._get_complete_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.COMPLETED, sprint.status)

    def test_complete_fails_for_non_active_sprint(self):
        """Cannot complete a sprint that is not active."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(self._get_complete_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.PLANNING, sprint.status)

    def test_complete_calculates_completed_points(self):
        """Completing a sprint calculates completed points."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            estimated_points=5,
            status=IssueStatus.DONE,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            estimated_points=3,
            status=IssueStatus.IN_PROGRESS,
        )

        self.client.post(self._get_complete_url(sprint))

        sprint.refresh_from_db()
        self.assertEqual(5, sprint.completed_points)

    def test_complete_moves_incomplete_issues(self):
        """Completing a sprint moves incomplete issues to next sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)
        next_sprint = SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.PLANNING,
            start_date=sprint.end_date + timedelta(days=1),
            end_date=sprint.end_date + timedelta(weeks=2),
        )
        epic = EpicFactory(project=self.project)
        done_story = StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.DONE,
            title="Done Story",
        )
        incomplete_story = StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.IN_PROGRESS,
            title="Incomplete Story",
        )

        self.client.post(self._get_complete_url(sprint))

        done_story.refresh_from_db()
        incomplete_story.refresh_from_db()
        self.assertEqual(sprint, done_story.sprint)
        self.assertEqual(next_sprint, incomplete_story.sprint)


class SprintArchiveViewTest(SprintViewTestBase):
    """Tests for the sprint archive action view."""

    def test_archive_sprint(self):
        """Can archive a completed sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)

        response = self.client.post(self._get_archive_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ARCHIVED, sprint.status)

    def test_archive_fails_for_active(self):
        """Cannot archive an active sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)

        response = self.client.post(self._get_archive_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ACTIVE, sprint.status)

    def test_archive_planning_sprint(self):
        """Can archive a planning sprint."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(self._get_archive_url(sprint))

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ARCHIVED, sprint.status)


class SprintIssuesEmbedViewTest(SprintViewTestBase):
    """Tests for the sprint embedded issue list view."""

    def test_sprint_issues_embed_returns_200(self):
        """Sprint issues embed view returns 200."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_issues_embed_url(sprint))

        self.assertEqual(200, response.status_code)

    def test_sprint_issues_embed_shows_only_sprint_issues(self):
        """Sprint issues embed only shows issues in the sprint."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=sprint, title="In Sprint")
        StoryFactory(project=self.project, parent=epic, sprint=None, title="Not In Sprint")

        response = self.client.get(self._get_issues_embed_url(sprint))

        self.assertContains(response, "In Sprint")
        self.assertNotContains(response, "Not In Sprint")

    def test_sprint_issues_embed_groups_by_status(self):
        """Sprint issues embed can group by status."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=sprint, status=IssueStatus.DRAFT)
        StoryFactory(
            project=self.project,
            parent=epic,
            sprint=sprint,
            status=IssueStatus.IN_PROGRESS,
        )

        response = self.client.get(self._get_issues_embed_url(sprint) + "?group_by=status")

        self.assertEqual(200, response.status_code)
        self.assertIn("grouped_issues", response.context)


class SprintAddIssuesViewTest(SprintViewTestBase):
    """Tests for adding issues to a sprint."""

    def test_add_issues_modal_returns_200(self):
        """Add issues modal returns 200."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_add_issues_url(sprint))

        self.assertEqual(200, response.status_code)

    def test_add_issues_filters_unassigned_issues(self):
        """Add issues modal shows only issues not in any sprint."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, sprint=None, title="Unassigned")
        StoryFactory(project=self.project, parent=epic, sprint=sprint, title="Already Assigned")

        response = self.client.get(self._get_add_issues_url(sprint))

        self.assertContains(response, "Unassigned")
        self.assertNotContains(response, "Already Assigned")

    def test_add_issues_to_sprint(self):
        """Can add issues to a sprint via POST."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=None, title="To Add")

        response = self.client.post(
            self._get_add_issues_url(sprint),
            {"issues": [story.key]},
        )

        self.assertEqual(302, response.status_code)
        story.refresh_from_db()
        self.assertEqual(sprint, story.sprint)


class SprintRemoveIssueViewTest(SprintViewTestBase):
    """Tests for removing issues from a sprint."""

    def test_remove_issue_from_sprint(self):
        """Can remove an issue from a sprint."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=sprint, title="To Remove")

        response = self.client.post(self._get_remove_issue_url(sprint, story.key))

        self.assertEqual(302, response.status_code)
        story.refresh_from_db()
        self.assertIsNone(story.sprint)

    def test_remove_issue_not_in_sprint(self):
        """Removing issue not in sprint shows warning."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=None, title="Not In Sprint")

        response = self.client.post(self._get_remove_issue_url(sprint, story.key))

        self.assertEqual(302, response.status_code)


class IssueAddToSprintViewTest(SprintViewTestBase):
    """Tests for adding a single issue to a sprint from the issue row menu."""

    def test_issue_add_to_sprint_modal_shows_sprints(self):
        """Modal shows available sprints."""
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.PLANNING,
            name="Planning Sprint",
        )
        SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE, name="Active Sprint")
        SprintFactory(
            workspace=self.workspace,
            status=SprintStatus.ARCHIVED,
            name="Archived Sprint",
        )
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=None)

        response = self.client.get(self._get_issue_add_to_sprint_url(story.key))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Planning Sprint")
        self.assertContains(response, "Active Sprint")
        self.assertNotContains(response, "Archived Sprint")

    def test_issue_add_to_sprint_shows_warning_if_already_assigned(self):
        """Modal shows warning if issue is already in a sprint."""
        existing_sprint = SprintFactory(workspace=self.workspace, name="Existing Sprint")
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=existing_sprint)

        response = self.client.get(self._get_issue_add_to_sprint_url(story.key))

        self.assertEqual(200, response.status_code)
        self.assertIn("current_sprint", response.context)
        self.assertEqual(existing_sprint, response.context["current_sprint"])

    def test_issue_add_to_sprint_confirm(self):
        """Can add issue to sprint via confirm POST."""
        sprint = SprintFactory(workspace=self.workspace)
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=None)

        response = self.client.post(
            self._get_issue_add_to_sprint_confirm_url(story.key),
            {"sprint": sprint.key},
        )

        self.assertEqual(302, response.status_code)
        story.refresh_from_db()
        self.assertEqual(sprint, story.sprint)

    def test_issue_add_to_sprint_confirm_replaces_existing(self):
        """Adding issue to sprint replaces existing sprint assignment."""
        old_sprint = SprintFactory(workspace=self.workspace, name="Old Sprint")
        new_sprint = SprintFactory(workspace=self.workspace, name="New Sprint")
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, sprint=old_sprint)

        response = self.client.post(
            self._get_issue_add_to_sprint_confirm_url(story.key),
            {"sprint": new_sprint.key},
        )

        self.assertEqual(302, response.status_code)
        story.refresh_from_db()
        self.assertEqual(new_sprint, story.sprint)


class SprintBulkDeleteViewTest(SprintViewTestBase):
    """Tests for bulk deleting sprints."""

    def _get_bulk_delete_url(self):
        return reverse(
            "sprints:sprints_bulk_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def test_bulk_delete_sprints(self):
        """Can delete multiple sprints at once."""
        sprint1 = SprintFactory(workspace=self.workspace, name="Sprint 1")
        sprint2 = SprintFactory(workspace=self.workspace, name="Sprint 2")
        sprint3 = SprintFactory(workspace=self.workspace, name="Sprint 3")

        response = self.client.post(
            self._get_bulk_delete_url(),
            {"sprints": [sprint1.key, sprint2.key]},
        )

        self.assertEqual(302, response.status_code)
        self.assertFalse(Sprint.objects.filter(pk=sprint1.pk).exists())
        self.assertFalse(Sprint.objects.filter(pk=sprint2.pk).exists())
        self.assertTrue(Sprint.objects.filter(pk=sprint3.pk).exists())

    def test_bulk_delete_no_selection(self):
        """Bulk delete with no selection shows warning."""
        SprintFactory(workspace=self.workspace)

        response = self.client.post(self._get_bulk_delete_url(), {"sprints": []})

        self.assertEqual(302, response.status_code)
        # Sprint should still exist
        self.assertEqual(1, Sprint.objects.for_workspace(self.workspace).count())


class SprintBulkStatusViewTest(SprintViewTestBase):
    """Tests for bulk updating sprint status."""

    def _get_bulk_status_url(self):
        return reverse(
            "sprints:sprints_bulk_status",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def test_bulk_status_update(self):
        """Can update status of multiple sprints (non-active status)."""
        sprint1 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        sprint2 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint1.key, sprint2.key], "status": SprintStatus.ARCHIVED},
        )

        self.assertEqual(302, response.status_code)
        sprint1.refresh_from_db()
        sprint2.refresh_from_db()
        self.assertEqual(SprintStatus.ARCHIVED, sprint1.status)
        self.assertEqual(SprintStatus.ARCHIVED, sprint2.status)

    def test_bulk_status_active_single_sprint_allowed(self):
        """Can set single sprint to active status."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint.key], "status": SprintStatus.ACTIVE},
        )

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ACTIVE, sprint.status)

    def test_bulk_status_active_multiple_sprints_rejected(self):
        """Cannot set multiple sprints to active status."""
        sprint1 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        sprint2 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint1.key, sprint2.key], "status": SprintStatus.ACTIVE},
        )

        self.assertEqual(302, response.status_code)
        sprint1.refresh_from_db()
        sprint2.refresh_from_db()
        # Both should still be in planning status
        self.assertEqual(SprintStatus.PLANNING, sprint1.status)
        self.assertEqual(SprintStatus.PLANNING, sprint2.status)

    def test_bulk_status_active_rejected_when_another_active(self):
        """Cannot set sprint to active when another is already active."""
        SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE, name="Already Active")
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint.key], "status": SprintStatus.ACTIVE},
        )

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        # Sprint should still be in planning status
        self.assertEqual(SprintStatus.PLANNING, sprint.status)

    def test_bulk_status_active_rejected_for_non_planning_sprint(self):
        """Cannot activate a sprint that is not in planning status."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint.key], "status": SprintStatus.ACTIVE},
        )

        self.assertEqual(302, response.status_code)
        sprint.refresh_from_db()
        # Sprint should still be in completed status
        self.assertEqual(SprintStatus.COMPLETED, sprint.status)

    def test_bulk_status_invalid_status(self):
        """Invalid status value shows error."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_bulk_status_url(),
            {"sprints": [sprint.key], "status": "invalid_status"},
        )

        self.assertEqual(302, response.status_code)


class SprintBulkOwnerViewTest(SprintViewTestBase):
    """Tests for bulk updating sprint owner."""

    def _get_bulk_owner_url(self):
        return reverse(
            "sprints:sprints_bulk_owner",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def test_bulk_owner_update(self):
        """Can update owner of multiple sprints."""
        sprint1 = SprintFactory(workspace=self.workspace, owner=None)
        sprint2 = SprintFactory(workspace=self.workspace, owner=None)

        response = self.client.post(
            self._get_bulk_owner_url(),
            {"sprints": [sprint1.key, sprint2.key], "owner": self.user.pk},
        )

        self.assertEqual(302, response.status_code)
        sprint1.refresh_from_db()
        sprint2.refresh_from_db()
        self.assertEqual(self.user, sprint1.owner)
        self.assertEqual(self.user, sprint2.owner)

    def test_bulk_owner_unassign(self):
        """Can unassign owner from multiple sprints."""
        sprint1 = SprintFactory(workspace=self.workspace, owner=self.user)
        sprint2 = SprintFactory(workspace=self.workspace, owner=self.user)

        response = self.client.post(
            self._get_bulk_owner_url(),
            {"sprints": [sprint1.key, sprint2.key], "owner": ""},
        )

        self.assertEqual(302, response.status_code)
        sprint1.refresh_from_db()
        sprint2.refresh_from_db()
        self.assertIsNone(sprint1.owner)
        self.assertIsNone(sprint2.owner)

    def test_bulk_owner_no_selection(self):
        """Bulk owner update with no selection shows warning."""
        SprintFactory(workspace=self.workspace)

        response = self.client.post(self._get_bulk_owner_url(), {"sprints": [], "owner": self.user.pk})

        self.assertEqual(302, response.status_code)


class SprintRowInlineEditViewTest(SprintViewTestBase):
    """Tests for the inline edit view for sprint rows."""

    def _get_inline_edit_url(self, sprint):
        return reverse(
            "sprints:sprint_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(sprint))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_row_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("sprint", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(sprint) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_row.html")

    def test_post_updates_sprint_name(self):
        """POST updates the sprint name."""
        sprint = SprintFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_inline_edit_url(sprint),
            {
                "name": "Updated Name",
                "status": sprint.status,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual("Updated Name", sprint.name)

    def test_post_updates_sprint_status(self):
        """POST updates the sprint status."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": SprintStatus.COMPLETED,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.COMPLETED, sprint.status)

    def test_post_updates_sprint_owner(self):
        """POST updates the sprint owner."""
        sprint = SprintFactory(workspace=self.workspace, owner=None)

        response = self.client.post(
            self._get_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": sprint.status,
                "owner": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(self.user, sprint.owner)

    def test_post_updates_sprint_capacity(self):
        """POST updates the sprint capacity."""
        sprint = SprintFactory(workspace=self.workspace, capacity=10)

        response = self.client.post(
            self._get_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": sprint.status,
                "capacity": 20,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(20, sprint.capacity)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_inline_edit_url(sprint),
            {
                "name": "",  # Required field
                "status": sprint.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_row_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)


class SprintDetailInlineEditViewTest(SprintViewTestBase):
    """Tests for the inline edit view for sprint detail page."""

    def _get_detail_inline_edit_url(self, sprint):
        return reverse(
            "sprints:sprint_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": sprint.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_inline_edit_url(sprint))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("sprint", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_detail_inline_edit_url(sprint) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_detail_header.html")

    def test_post_updates_sprint_name(self):
        """POST updates the sprint name."""
        sprint = SprintFactory(workspace=self.workspace, name="Original Name")

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": "Updated Name",
                "status": sprint.status,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual("Updated Name", sprint.name)

    def test_post_updates_sprint_goal(self):
        """POST updates the sprint goal."""
        sprint = SprintFactory(workspace=self.workspace, goal="Original goal")

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": sprint.status,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
                "goal": "Updated goal",
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual("Updated goal", sprint.goal)

    def test_post_updates_sprint_status(self):
        """POST updates the sprint status."""
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": SprintStatus.COMPLETED,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.COMPLETED, sprint.status)

    def test_post_updates_sprint_owner(self):
        """POST updates the sprint owner."""
        sprint = SprintFactory(workspace=self.workspace, owner=None)

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": sprint.status,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
                "owner": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(self.user, sprint.owner)

    def test_post_updates_sprint_capacity(self):
        """POST updates the sprint capacity."""
        sprint = SprintFactory(workspace=self.workspace, capacity=10)

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": sprint.name,
                "status": sprint.status,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
                "capacity": 20,
            },
        )

        self.assertEqual(200, response.status_code)
        sprint.refresh_from_db()
        self.assertEqual(20, sprint.capacity)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.post(
            self._get_detail_inline_edit_url(sprint),
            {
                "name": "",  # Required field
                "status": sprint.status,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "sprints/includes/sprint_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)
