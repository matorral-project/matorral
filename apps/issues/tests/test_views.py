from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, MilestoneFactory, StoryFactory
from apps.issues.models import BaseIssue, BugSeverity, Epic, IssuePriority, IssueStatus, Milestone
from apps.projects.factories import ProjectFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class IssueViewTestBase(TestCase):
    """Base test class for issue views."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_detail_url(self, issue):
        return reverse(
            "issues:issue_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_create_url(self, issue_type="story"):
        return reverse(
            "issues:issue_create_typed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "issue_type": issue_type,
            },
        )

    def _get_update_url(self, issue):
        return reverse(
            "issues:issue_update",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_delete_url(self, issue):
        return reverse(
            "issues:issue_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def _get_clone_url(self, issue):
        return reverse(
            "issues:issue_clone",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )


class IssueDetailViewTest(IssueViewTestBase):
    """Tests for the issue detail view."""

    def test_detail_view_returns_200(self):
        """Detail view returns 200 for existing issue."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_detail_url(epic))

        self.assertEqual(200, response.status_code)

    def test_detail_view_shows_issue_info(self):
        """Detail view displays issue information."""
        epic = EpicFactory(project=self.project, title="Feature Epic", description="Epic description")

        response = self.client.get(self._get_detail_url(epic))

        self.assertContains(response, "Feature Epic")
        self.assertContains(response, "Epic description")
        self.assertContains(response, epic.key)

    def test_detail_view_shows_children(self):
        """Detail view includes lazy-load URL for epic children."""
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, title="Child Story")

        response = self.client.get(self._get_detail_url(epic))

        # Epic detail now uses lazy-loading for children, verify the URL is present
        embed_url = reverse(
            "issues:epic_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": epic.key,
            },
        )
        self.assertContains(response, embed_url)

    def test_epic_issues_embed_view(self):
        """Epic issues embed view shows child issues."""
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, title="Child Story")

        embed_url = reverse(
            "issues:epic_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": epic.key,
            },
        )
        response = self.client.get(embed_url)

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Child Story")

    def test_epic_issues_embed_view_with_sprint_grouping(self):
        """Epic issues embed view works with sprint grouping."""
        from apps.sprints.factories import SprintFactory

        epic = EpicFactory(project=self.project)
        sprint = SprintFactory(workspace=self.workspace, name="Test Sprint")
        StoryFactory(project=self.project, parent=epic, title="Story in Sprint", sprint=sprint)
        StoryFactory(project=self.project, parent=epic, title="Story without Sprint")

        embed_url = reverse(
            "issues:epic_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": epic.key,
            },
        )
        response = self.client.get(embed_url + "?group_by=sprint")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Story in Sprint")
        self.assertContains(response, "Story without Sprint")
        self.assertContains(response, "Test Sprint")

    def test_detail_view_404_for_nonexistent(self):
        """Detail view returns 404 for nonexistent issue."""
        response = self.client.get(
            reverse(
                "issues:issue_detail",
                kwargs={
                    "workspace_slug": self.workspace.slug,
                    "project_key": self.project.key,
                    "key": "NONEXISTENT",
                },
            )
        )

        self.assertEqual(404, response.status_code)

    def test_htmx_history_restore_returns_full_page(self):
        """HTMX history-restore request returns the full page template, not a fragment."""
        epic = EpicFactory(project=self.project)
        url = self._get_detail_url(epic)

        # Regular HTMX request → partial fragment (contains "#page-content" marker)
        htmx_response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(200, htmx_response.status_code)

        # History-restore HTMX request → full page (same as non-HTMX)
        restore_response = self.client.get(
            url,
            HTTP_HX_REQUEST="true",
            HTTP_HX_HISTORY_RESTORE_REQUEST="true",
        )
        self.assertEqual(200, restore_response.status_code)
        # Full page response must contain the base <html> tag
        self.assertContains(restore_response, "<html")


class IssueCreateViewTest(IssueViewTestBase):
    """Tests for the issue create view."""

    def test_create_view_returns_200(self):
        """Create view returns 200."""
        response = self.client.get(self._get_create_url("epic"))

        self.assertEqual(200, response.status_code)

    def test_create_epic(self):
        """Can create an epic via POST."""
        response = self.client.post(
            self._get_create_url("epic"),
            {
                "project": self.project.pk,
                "title": "New Epic",
                "status": IssueStatus.DRAFT,
                "priority": "medium",
            },
        )

        self.assertEqual(302, response.status_code)
        self.assertTrue(BaseIssue.objects.filter(title="New Epic").exists())

    def test_create_story_with_parent(self):
        """Creating a story with an epic parent."""
        epic = EpicFactory(project=self.project)

        response = self.client.post(
            self._get_create_url("story"),
            {
                "project": self.project.pk,
                "title": "New Story",
                "description": "",
                "status": IssueStatus.DRAFT,
                "priority": "medium",
                "parent": epic.pk,
                "estimated_points": "",
            },
        )

        self.assertEqual(302, response.status_code)
        self.assertTrue(BaseIssue.objects.filter(title="New Story").exists())


class IssueUpdateViewTest(IssueViewTestBase):
    """Tests for the issue update view."""

    def test_update_view_returns_200(self):
        """Update view returns 200."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_update_url(epic))

        self.assertEqual(200, response.status_code)

    def test_update_issue(self):
        """Can update an issue via POST."""
        epic = EpicFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_update_url(epic),
            {
                "project": self.project.pk,
                "title": "Updated Title",
                "status": IssueStatus.IN_PROGRESS,
                "priority": "high",
            },
        )

        self.assertEqual(302, response.status_code)
        epic.refresh_from_db()
        self.assertEqual("Updated Title", epic.title)


class IssueDeleteViewTest(IssueViewTestBase):
    """Tests for the issue delete view."""

    def test_delete_view_returns_200(self):
        """Delete view returns 200."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_delete_url(epic))

        self.assertEqual(200, response.status_code)

    def test_delete_issue(self):
        """Can delete an issue via POST."""
        epic = EpicFactory(project=self.project)
        issue_pk = epic.pk

        response = self.client.post(self._get_delete_url(epic))

        self.assertEqual(302, response.status_code)
        self.assertFalse(BaseIssue.objects.filter(pk=issue_pk).exists())

    def test_delete_shows_descendant_count(self):
        """Delete view shows count of child issues that will be deleted."""
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic)
        StoryFactory(project=self.project, parent=epic)

        response = self.client.get(self._get_delete_url(epic))

        self.assertContains(response, "2 child issues")

    def test_delete_epic_cascades_to_children(self):
        """Deleting an epic via the view also deletes its children."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic, title="Child Story")
        bug = StoryFactory(project=self.project, parent=epic, title="Child Bug")

        # Store IDs
        epic_id = epic.pk
        story_id = story.pk
        bug_id = bug.pk

        # Delete via view (POST to delete URL)
        response = self.client.post(self._get_delete_url(epic))

        self.assertEqual(302, response.status_code)
        # Verify all are deleted
        self.assertFalse(BaseIssue.objects.filter(pk=epic_id).exists())
        self.assertFalse(BaseIssue.objects.filter(pk=story_id).exists())
        self.assertFalse(BaseIssue.objects.filter(pk=bug_id).exists())


class IssueCloneViewTest(IssueViewTestBase):
    """Tests for the issue clone view."""

    def test_clone_creates_copy(self):
        """Clone creates a copy of the issue."""
        epic = EpicFactory(project=self.project, title="Original Epic")

        response = self.client.post(self._get_clone_url(epic))

        self.assertEqual(302, response.status_code)
        self.assertEqual(2, BaseIssue.objects.for_project(self.project).count())
        self.assertTrue(BaseIssue.objects.filter(title__contains="(Copy)").exists())

    def test_clone_preserves_fields(self):
        """Clone preserves all fields except title and key."""
        epic = EpicFactory(
            project=self.project,
            title="Original",
            description="Test description",
            status=IssueStatus.IN_PROGRESS,
        )

        self.client.post(self._get_clone_url(epic))

        cloned = BaseIssue.objects.filter(title__contains="(Copy)").first()
        self.assertEqual("Test description", cloned.description)
        self.assertEqual(IssueStatus.IN_PROGRESS, cloned.status)
        self.assertNotEqual(epic.key, cloned.key)


class IssueMoveViewTest(IssueViewTestBase):
    """Tests for the issue move view."""

    def _get_move_url(self, issue):
        return reverse(
            "issues:issue_move",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_move_view_returns_200(self):
        """GET returns modal content with valid parents."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic)

        response = self.client.get(self._get_move_url(story))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, epic.key)

    def test_get_move_view_shows_only_epics_for_story(self):
        """GET shows only epic parents for stories."""
        epic1 = EpicFactory(project=self.project, title="Epic 1")
        epic2 = EpicFactory(project=self.project, title="Epic 2")
        story = StoryFactory(project=self.project, parent=epic1, title="Test Story")

        response = self.client.get(self._get_move_url(story))

        self.assertEqual(200, response.status_code)
        # Check epics are in the valid_parents list
        valid_parents = response.context["valid_parents"]
        valid_parent_keys = [p.key for p in valid_parents]
        self.assertIn(epic1.key, valid_parent_keys)
        self.assertIn(epic2.key, valid_parent_keys)
        # Story should not be in valid parents
        self.assertNotIn(story.key, valid_parent_keys)

    def test_get_move_view_shows_only_epics_for_bug(self):
        """GET shows only epic parents for bugs."""
        epic = EpicFactory(project=self.project, title="Parent Epic")
        bug = BugFactory(project=self.project, parent=epic, title="Test Bug")

        response = self.client.get(self._get_move_url(bug))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, epic.key)

    def test_get_move_view_shows_only_epics_for_chore(self):
        """GET shows only epic parents for chores."""
        epic = EpicFactory(project=self.project, title="Parent Epic")
        chore = ChoreFactory(project=self.project, parent=epic, title="Test Chore")

        response = self.client.get(self._get_move_url(chore))

        self.assertEqual(200, response.status_code)
        self.assertContains(response, epic.key)

    def test_post_move_story_to_epic(self):
        """POST moves a story under a new epic parent."""
        epic1 = EpicFactory(project=self.project, title="Old Epic")
        epic2 = EpicFactory(project=self.project, title="New Epic")
        story = StoryFactory(project=self.project, parent=epic1, title="Test Story")

        response = self.client.post(self._get_move_url(story), {"parent_key": epic2.key})

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(epic2.pk, story.get_parent().pk)

    def test_post_move_story_to_root(self):
        """POST moves a story to root level (no parent)."""
        epic = EpicFactory(project=self.project, title="Parent Epic")
        story = StoryFactory(project=self.project, parent=epic, title="Test Story")

        response = self.client.post(self._get_move_url(story), {"parent_key": ""})

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertIsNone(story.get_parent())

    def test_post_move_story_rejects_non_epic_parent(self):
        """POST rejects moving a story to a non-epic parent."""
        epic = EpicFactory(project=self.project)
        story1 = StoryFactory(project=self.project, parent=epic, title="Story 1")
        story2 = StoryFactory(project=self.project, parent=epic, title="Story 2")

        response = self.client.post(self._get_move_url(story1), {"parent_key": story2.key})

        # Should return error response (400 for non-HTMX requests)
        self.assertEqual(400, response.status_code)
        # Story should not have moved
        story1.refresh_from_db()
        self.assertEqual(epic.pk, story1.get_parent().pk)

    def test_post_move_returns_refresh_header(self):
        """POST returns HX-Refresh header for HTMX requests."""
        epic1 = EpicFactory(project=self.project)
        epic2 = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project, parent=epic1)

        response = self.client.post(
            self._get_move_url(story),
            {"parent_key": epic2.key},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("true", response["HX-Refresh"])


class WorkspaceIssueListViewTest(IssueViewTestBase):
    """Tests for the workspace issue list view."""

    def _get_workspace_list_url(self):
        return reverse(
            "workspace_issue_list",
            kwargs={
                "workspace_slug": self.workspace.slug,
            },
        )

    def test_list_view_returns_200(self):
        """List view returns 200 for authenticated workspace member."""
        response = self.client.get(self._get_workspace_list_url())

        self.assertEqual(200, response.status_code)

    def test_list_view_shows_issues_from_all_projects(self):
        """List view shows work items from all projects in workspace."""
        project2 = ProjectFactory(workspace=self.workspace)
        epic1 = EpicFactory(project=self.project)
        epic2 = EpicFactory(project=project2)
        StoryFactory(project=self.project, parent=epic1, title="Story from Project 1")
        StoryFactory(project=project2, parent=epic2, title="Story from Project 2")

        response = self.client.get(self._get_workspace_list_url())

        self.assertContains(response, "Story from Project 1")
        self.assertContains(response, "Story from Project 2")

    def test_list_view_group_by_epic(self):
        """List view can group issues by epic when filtering by project."""
        epic1 = EpicFactory(project=self.project, title="Feature Epic")
        epic2 = EpicFactory(project=self.project, title="Bug Fix Epic")
        StoryFactory(project=self.project, parent=epic1, title="Story 1")
        StoryFactory(project=self.project, parent=epic2, title="Story 2")

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}&group_by=epic")

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context["is_paginated"])
        self.assertIn("grouped_issues", response.context)
        self.assertContains(response, "Feature Epic")
        self.assertContains(response, "Bug Fix Epic")

    def test_list_view_group_by_status(self):
        """List view can group issues by status when filtering by project."""
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            title="Draft Story",
            status=IssueStatus.DRAFT,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            title="In Progress Story",
            status=IssueStatus.IN_PROGRESS,
        )

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}&group_by=status")

        self.assertEqual(200, response.status_code)
        self.assertIn("grouped_issues", response.context)
        self.assertEqual("status", response.context["group_by"])
        self.assertEqual("Status", response.context["group_by_label"])

    def test_list_view_group_by_priority(self):
        """List view can group issues by priority when filtering by project."""
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            title="High Priority",
            priority=IssuePriority.HIGH,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            title="Low Priority",
            priority=IssuePriority.LOW,
        )

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}&group_by=priority")

        self.assertEqual(200, response.status_code)
        self.assertIn("grouped_issues", response.context)
        self.assertContains(response, "High")
        self.assertContains(response, "Low")

    def test_list_view_group_by_assignee(self):
        """List view can group issues by assignee when filtering by project."""
        epic = EpicFactory(project=self.project)
        StoryFactory(
            project=self.project,
            parent=epic,
            title="Assigned Story",
            assignee=self.user,
        )
        StoryFactory(project=self.project, parent=epic, title="Unassigned Story", assignee=None)

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}&group_by=assignee")

        self.assertEqual(200, response.status_code)
        self.assertIn("grouped_issues", response.context)
        self.assertContains(response, "Unassigned")

    def test_list_view_group_by_disables_pagination(self):
        """List view with group_by disables pagination when filtering by project."""
        epic = EpicFactory(project=self.project)
        for i in range(20):
            StoryFactory(project=self.project, parent=epic, title=f"Story {i}")

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}&group_by=status")

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context["is_paginated"])

    def test_list_view_group_by_ignored_without_project_filter(self):
        """List view ignores group_by when not filtering by project."""
        epic = EpicFactory(project=self.project)
        StoryFactory(project=self.project, parent=epic, title="Story 1")

        response = self.client.get(self._get_workspace_list_url() + "?group_by=status")

        self.assertEqual(200, response.status_code)
        # group_by should be empty since no project filter
        self.assertEqual("", response.context["group_by"])
        self.assertNotIn("grouped_issues", response.context)

    def test_list_view_group_by_choices_context(self):
        """List view includes group_by_choices in context when filtering by project."""
        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}")

        self.assertIn("group_by_choices", response.context)
        choices = response.context["group_by_choices"]
        # Workspace list should have epic, status, priority, assignee
        choice_values = [c[0] for c in choices]
        self.assertIn("epic", choice_values)
        self.assertIn("status", choice_values)
        self.assertIn("priority", choice_values)
        self.assertIn("assignee", choice_values)
        # No project option for workspace level
        self.assertNotIn("project", choice_values)

    def test_list_view_filter_by_project(self):
        """List view can filter issues by project key."""
        project2 = ProjectFactory(workspace=self.workspace, name="Second Project")
        epic1 = EpicFactory(project=self.project)
        epic2 = EpicFactory(project=project2)
        StoryFactory(project=self.project, parent=epic1, title="Story from Project 1")
        StoryFactory(project=project2, parent=epic2, title="Story from Project 2")

        response = self.client.get(self._get_workspace_list_url() + f"?project={self.project.key}")

        self.assertEqual(200, response.status_code)
        self.assertContains(response, "Story from Project 1")
        self.assertNotContains(response, "Story from Project 2")
        self.assertEqual(self.project.key, response.context["project_filter"])

    def test_list_view_filter_by_project_invalid_key_returns_404(self):
        """List view returns 404 for invalid project key."""
        response = self.client.get(self._get_workspace_list_url() + "?project=INVALID")

        self.assertEqual(404, response.status_code)


class MilestoneViewTestBase(TestCase):
    """Base test class for milestone views."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_detail_url(self, milestone):
        return reverse(
            "milestones:milestone_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def _get_create_url(self):
        return reverse(
            "milestones:milestone_create",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
            },
        )

    def _get_update_url(self, milestone):
        return reverse(
            "milestones:milestone_update",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def _get_delete_url(self, milestone):
        return reverse(
            "milestones:milestone_delete",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )


class MilestoneDetailViewTest(MilestoneViewTestBase):
    """Tests for the milestone detail view."""

    def test_detail_view_returns_200(self):
        """Detail view returns 200 for existing milestone."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_detail_url(milestone))

        self.assertEqual(200, response.status_code)

    def test_detail_view_shows_milestone_info(self):
        """Detail view displays milestone information."""
        milestone = MilestoneFactory(project=self.project, title="Release 1.0", description="First release")

        response = self.client.get(self._get_detail_url(milestone))

        self.assertContains(response, "Release 1.0")
        self.assertContains(response, "First release")
        self.assertContains(response, milestone.key)

    def test_detail_view_loads_issues_embed(self):
        """Detail view loads the embedded issues list via HTMX."""
        milestone = MilestoneFactory(project=self.project)
        EpicFactory(project=self.project, title="Linked Epic", milestone=milestone)

        response = self.client.get(self._get_detail_url(milestone))

        # Embedded issues are loaded via HTMX, check for the HTMX URL
        self.assertContains(response, f"/milestones/{milestone.key}/issues/")
        self.assertContains(response, 'hx-trigger="load"')

    def test_detail_view_shows_progress(self):
        """Detail view shows overall milestone progress."""
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone)
        StoryFactory(
            project=self.project,
            parent=epic,
            status=IssueStatus.DONE,
            estimated_points=3,
        )
        StoryFactory(
            project=self.project,
            parent=epic,
            status=IssueStatus.DRAFT,
            estimated_points=7,
        )

        response = self.client.get(self._get_detail_url(milestone))

        # 30% done (3 of 10 points)
        self.assertEqual(response.context["progress"]["done_pct"], 30)
        self.assertEqual(response.context["progress"]["todo_pct"], 70)

    def test_detail_view_loads_issues_embed_with_new_epic_button(self):
        """Detail view loads issues embed which contains New Epic button."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_detail_url(milestone))

        # The detail view loads the embed via HTMX, so we just check the embed URL is present
        self.assertContains(response, f"/milestones/{milestone.key}/issues/?group_by=epic")


class MilestoneIssueListEmbedViewTest(MilestoneViewTestBase):
    """Tests for the milestone issues embed view."""

    def _get_embed_url(self, milestone):
        return reverse(
            "milestones:milestone_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_embed_view_returns_200(self):
        """Embed view returns 200."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_embed_url(milestone))

        self.assertEqual(200, response.status_code)

    def test_embed_view_shows_linked_epic_issues(self):
        """Embed view shows issues from epics linked to the milestone."""
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, title="Linked Epic", milestone=milestone)
        StoryFactory(project=self.project, parent=epic, title="Story in Epic")

        response = self.client.get(self._get_embed_url(milestone) + "?group_by=epic")

        self.assertContains(response, "Story in Epic")
        self.assertContains(response, "Linked Epic")

    def test_embed_view_excludes_unlinked_epic_issues(self):
        """Embed view excludes issues from epics not linked to the milestone."""
        milestone = MilestoneFactory(project=self.project)
        # Epic with no milestone link
        unlinked_epic = EpicFactory(project=self.project, title="Unlinked Epic")
        StoryFactory(project=self.project, parent=unlinked_epic, title="Story in Unlinked Epic")

        response = self.client.get(self._get_embed_url(milestone))

        self.assertNotContains(response, "Story in Unlinked Epic")

    def test_embed_view_grouped_by_epic(self):
        """Embed view shows issues grouped by epic when group_by=epic."""
        milestone = MilestoneFactory(project=self.project)
        epic = EpicFactory(project=self.project, milestone=milestone, title="Test Epic")
        StoryFactory(project=self.project, parent=epic, title="Epic Story")

        response = self.client.get(self._get_embed_url(milestone) + "?group_by=epic")

        self.assertIn("grouped_issues", response.context)
        grouped = response.context["grouped_issues"]
        self.assertEqual(len(grouped), 1)
        self.assertIn("Test Epic", grouped[0]["name"])

    def test_embed_view_shows_new_epic_button(self):
        """Embed view shows New Epic button that opens modal."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_embed_url(milestone))

        # Check for "New Epic" button with modal parameter
        self.assertContains(response, "New Epic")
        self.assertContains(response, f"/milestones/{milestone.key}/new-epic/?modal=1")


class MilestoneCreateViewTest(MilestoneViewTestBase):
    """Tests for the milestone create view."""

    def test_create_view_returns_200(self):
        """Create view returns 200."""
        response = self.client.get(self._get_create_url())

        self.assertEqual(200, response.status_code)

    def test_create_milestone(self):
        """Can create a milestone via POST."""
        response = self.client.post(
            self._get_create_url(),
            {
                "title": "New Milestone",
                "description": "Description",
                "status": IssueStatus.DRAFT,
                "priority": "medium",
            },
        )

        self.assertEqual(302, response.status_code)
        self.assertTrue(Milestone.objects.filter(title="New Milestone").exists())


class MilestoneUpdateViewTest(MilestoneViewTestBase):
    """Tests for the milestone update view."""

    def test_update_view_returns_200(self):
        """Update view returns 200."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_update_url(milestone))

        self.assertEqual(200, response.status_code)

    def test_update_milestone(self):
        """Can update a milestone via POST."""
        milestone = MilestoneFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_update_url(milestone),
            {
                "title": "Updated Title",
                "status": IssueStatus.IN_PROGRESS,
                "priority": "high",
            },
        )

        self.assertEqual(302, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual("Updated Title", milestone.title)


class MilestoneDeleteViewTest(MilestoneViewTestBase):
    """Tests for the milestone delete view."""

    def test_delete_view_returns_200(self):
        """Delete view returns 200."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_delete_url(milestone))

        self.assertEqual(200, response.status_code)

    def test_delete_milestone(self):
        """Can delete a milestone via POST."""
        milestone = MilestoneFactory(project=self.project)
        milestone_pk = milestone.pk

        response = self.client.post(self._get_delete_url(milestone))

        self.assertEqual(302, response.status_code)
        self.assertFalse(Milestone.objects.filter(pk=milestone_pk).exists())


class MilestoneCloneViewTest(MilestoneViewTestBase):
    """Tests for the milestone clone view."""

    def _get_clone_url(self, milestone):
        return reverse(
            "milestones:milestone_clone",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_clone_milestone(self):
        """Can clone a milestone via POST."""
        milestone = MilestoneFactory(
            project=self.project,
            title="Original Milestone",
            description="Original description",
            status=IssueStatus.IN_PROGRESS,
            priority=IssuePriority.HIGH,
            owner=self.user,
        )
        original_count = Milestone.objects.count()

        response = self.client.post(self._get_clone_url(milestone))

        self.assertEqual(302, response.status_code)
        self.assertEqual(original_count + 1, Milestone.objects.count())
        cloned = Milestone.objects.exclude(pk=milestone.pk).get()
        self.assertEqual(f"{milestone.title} (Copy)", cloned.title)
        self.assertEqual(milestone.description, cloned.description)
        self.assertEqual(milestone.status, cloned.status)
        self.assertEqual(milestone.priority, cloned.priority)
        self.assertEqual(milestone.owner, cloned.owner)
        self.assertNotEqual(milestone.key, cloned.key)

    def test_clone_redirects_to_cloned_milestone(self):
        """Clone redirects to the cloned milestone detail page."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(self._get_clone_url(milestone))

        cloned = Milestone.objects.exclude(pk=milestone.pk).get()
        self.assertRedirects(response, cloned.get_absolute_url())


class MilestoneRowInlineEditViewTest(MilestoneViewTestBase):
    """Tests for the inline edit view for milestone rows."""

    def _get_inline_edit_url(self, milestone):
        return reverse(
            "milestones:milestone_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(milestone))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_row_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("milestone", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(milestone) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_row.html")

    def test_post_updates_milestone_title(self):
        """POST updates the milestone title."""
        milestone = MilestoneFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": "Updated Title",
                "status": milestone.status,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual("Updated Title", milestone.title)

    def test_post_updates_milestone_status(self):
        """POST updates the milestone status."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": IssueStatus.IN_PROGRESS,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, milestone.status)

    def test_post_updates_milestone_priority(self):
        """POST updates the milestone priority."""
        milestone = MilestoneFactory(project=self.project, priority=IssuePriority.LOW)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": milestone.status,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, milestone.priority)

    def test_post_updates_milestone_owner(self):
        """POST updates the milestone owner."""
        milestone = MilestoneFactory(project=self.project, owner=None)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": milestone.status,
                "owner": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(self.user, milestone.owner)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": "",  # Required field
                "status": milestone.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_row_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)


class MilestoneDetailInlineEditViewTest(MilestoneViewTestBase):
    """Tests for the inline edit view for milestone details page."""

    def _get_inline_edit_url(self, milestone):
        return reverse(
            "milestones:milestone_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(milestone))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("milestone", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(milestone) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_detail_header.html")

    def test_post_updates_milestone_title(self):
        """POST updates the milestone title."""
        milestone = MilestoneFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": "Updated Title",
                "status": milestone.status,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual("Updated Title", milestone.title)

    def test_post_updates_milestone_description(self):
        """POST updates the milestone description."""
        milestone = MilestoneFactory(project=self.project, description="Original description")

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": milestone.status,
                "description": "Updated description",
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual("Updated description", milestone.description)

    def test_post_updates_milestone_status(self):
        """POST updates the milestone status."""
        milestone = MilestoneFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": IssueStatus.IN_PROGRESS,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, milestone.status)

    def test_post_updates_milestone_priority(self):
        """POST updates the milestone priority."""
        milestone = MilestoneFactory(project=self.project, priority=IssuePriority.LOW)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": milestone.status,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, milestone.priority)

    def test_post_updates_milestone_owner(self):
        """POST updates the milestone owner."""
        milestone = MilestoneFactory(project=self.project, owner=None)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": milestone.title,
                "status": milestone.status,
                "owner": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        milestone.refresh_from_db()
        self.assertEqual(self.user, milestone.owner)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(milestone),
            {
                "title": "",  # Required field
                "status": milestone.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/milestone_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)


class MilestoneEpicCreateViewTest(MilestoneViewTestBase):
    """Tests for the milestone-level epic create view (from milestone detail)."""

    def _get_new_epic_url(self, milestone):
        return reverse(
            "milestones:milestone_new_epic",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": milestone.key,
            },
        )

    def test_get_returns_200(self):
        """GET request returns 200 and shows form."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_new_epic_url(milestone))

        self.assertEqual(200, response.status_code)
        self.assertIn("form", response.context)
        self.assertIn("milestone", response.context)
        self.assertEqual(milestone, response.context["milestone"])

    def test_create_epic(self):
        """POST creates an epic linked to the milestone."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(
            self._get_new_epic_url(milestone),
            {
                "title": "Test Epic",
                "status": IssueStatus.DRAFT,
                "priority": "medium",
            },
        )

        # Should redirect to milestone detail
        self.assertRedirects(response, milestone.get_absolute_url())

        # Epic should be created and linked to milestone
        epic = Epic.objects.get(title="Test Epic")
        self.assertEqual(milestone, epic.milestone)
        self.assertEqual(self.project, epic.project)

    def test_form_project_field_hidden(self):
        """Form does not show project field since it's preset from milestone."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_new_epic_url(milestone))

        form = response.context["form"]
        self.assertNotIn("project", form.fields)

    def test_form_milestone_field_hidden(self):
        """Form does not show milestone field since it's preset."""
        milestone = MilestoneFactory(project=self.project)

        response = self.client.get(self._get_new_epic_url(milestone))

        form = response.context["form"]
        self.assertNotIn("milestone", form.fields)


class IssueRowInlineEditViewTest(IssueViewTestBase):
    """Tests for the inline edit view for issue rows."""

    def _get_inline_edit_url(self, issue):
        return reverse(
            "issues:issue_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("issue", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row.html")

    def test_post_updates_issue_title(self):
        """POST updates the issue title."""
        story = StoryFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": "Updated Title",
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual("Updated Title", story.title)

    def test_post_updates_issue_status(self):
        """POST updates the issue status."""
        story = StoryFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": IssueStatus.IN_PROGRESS,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, story.status)

    def test_post_updates_issue_priority(self):
        """POST updates the issue priority."""
        story = StoryFactory(project=self.project, priority=IssuePriority.LOW)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, story.priority)

    def test_post_updates_issue_assignee(self):
        """POST updates the issue assignee."""
        story = StoryFactory(project=self.project, assignee=None)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "priority": story.priority,
                "assignee": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(self.user, story.assignee)

    def test_post_updates_estimated_points(self):
        """POST updates estimated points for work items."""
        story = StoryFactory(project=self.project, estimated_points=None)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "priority": story.priority,
                "estimated_points": 5,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(5, story.estimated_points)

    def test_post_returns_display_template_on_success(self):
        """POST returns display template after successful update."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": "Updated",
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row.html")

    def test_post_returns_edit_template_on_validation_error(self):
        """POST returns edit template when validation fails."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": "",  # Empty title should fail validation
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_edit.html")
        # Title should not have changed
        story.refresh_from_db()
        self.assertNotEqual("", story.title)

    def test_epic_inline_edit(self):
        """Can inline edit an epic."""
        epic = EpicFactory(project=self.project, title="Original Epic")

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": "Updated Epic",
                "status": IssueStatus.IN_PROGRESS,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual("Updated Epic", epic.title)
        self.assertEqual(IssueStatus.IN_PROGRESS, epic.status)
        self.assertEqual(IssuePriority.HIGH, epic.priority)

    def test_show_columns_params_respected(self):
        """Column visibility params are passed to context."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?show_status=0")

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context["show_status"])
        self.assertTrue(response.context["show_priority"])
        self.assertTrue(response.context["show_assignee"])

    def test_embed_get_returns_embed_edit_template(self):
        """GET with embed=1 returns the embed edit template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?embed=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_edit_embed.html")
        self.assertTrue(response.context["is_embed"])

    def test_embed_get_with_cancel_returns_embed_display_template(self):
        """GET with embed=1&cancel=1 returns the embed display template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?embed=1&cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_embed.html")

    def test_embed_post_returns_embed_display_template_on_success(self):
        """POST with embed=1 returns embed display template after successful update."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story) + "?embed=1",
            {
                "title": "Updated",
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_embed.html")

    def test_embed_post_returns_embed_edit_template_on_validation_error(self):
        """POST with embed=1 returns embed edit template when validation fails."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story) + "?embed=1",
            {
                "title": "",  # Empty title should fail validation
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_row_edit_embed.html")

    def test_embed_sprint_context_is_loaded(self):
        """GET with embed=1&sprint=KEY loads the sprint context."""
        from apps.sprints.factories import SprintFactory

        story = StoryFactory(project=self.project)
        sprint = SprintFactory(workspace=self.workspace)

        response = self.client.get(self._get_inline_edit_url(story) + f"?embed=1&sprint={sprint.key}")

        self.assertEqual(200, response.status_code)
        self.assertEqual(sprint, response.context["sprint"])
        self.assertTrue(response.context["show_project"])

    # Dashboard context tests

    def test_dashboard_get_returns_dashboard_edit_template(self):
        """GET with dashboard=1 returns the dashboard edit template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?dashboard=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "includes/dashboard_issue_row_edit.html")
        self.assertTrue(response.context["is_dashboard"])

    def test_dashboard_get_with_cancel_returns_dashboard_display_template(self):
        """GET with dashboard=1&cancel=1 returns the dashboard display template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?dashboard=1&cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "workspaces/includes/dashboard_issue_row.html")

    def test_dashboard_post_returns_dashboard_display_template_on_success(self):
        """POST with dashboard=1 returns dashboard display template after successful update."""
        story = StoryFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(story) + "?dashboard=1",
            {
                "title": "Updated Title",
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "workspaces/includes/dashboard_issue_row.html")
        story.refresh_from_db()
        self.assertEqual("Updated Title", story.title)

    def test_dashboard_post_returns_dashboard_edit_template_on_validation_error(self):
        """POST with dashboard=1 returns dashboard edit template when validation fails."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story) + "?dashboard=1",
            {
                "title": "",  # Empty title triggers validation error
                "status": story.status,
                "priority": story.priority,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "includes/dashboard_issue_row_edit.html")

    def test_dashboard_post_preserves_assignee_and_points(self):
        """POST from dashboard preserves assignee and estimated_points via hidden fields."""
        story = StoryFactory(
            project=self.project,
            title="Original Title",
            assignee=self.user,
            estimated_points=5,
        )

        response = self.client.post(
            self._get_inline_edit_url(story) + "?dashboard=1",
            {
                "title": "Updated Title",
                "status": story.status,
                "priority": story.priority,
                "assignee": self.user.pk,  # Hidden field value
                "estimated_points": 5,  # Hidden field value
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual("Updated Title", story.title)
        self.assertEqual(self.user, story.assignee)
        self.assertEqual(5, story.estimated_points)

    def test_dashboard_post_with_hidden_field_returns_dashboard_template(self):
        """POST with dashboard=1 in POST data (not query string) returns dashboard template."""
        story = StoryFactory(project=self.project, title="Original Title")

        # Simulate how HTMX sends the request with hidden field instead of query string
        response = self.client.post(
            self._get_inline_edit_url(story),  # No ?dashboard=1 in URL
            {
                "title": "Updated Title",
                "status": story.status,
                "priority": story.priority,
                "dashboard": "1",  # Hidden field value
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "workspaces/includes/dashboard_issue_row.html")


class EpicDetailInlineEditViewTest(IssueViewTestBase):
    """Tests for the inline edit view for epic details page."""

    def _get_inline_edit_url(self, epic):
        return reverse(
            "issues:epic_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": epic.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(epic))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/epic_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("issue", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        epic = EpicFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(epic) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/epic_detail_header.html")

    def test_post_updates_epic_title(self):
        """POST updates the epic title."""
        epic = EpicFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": "Updated Title",
                "status": epic.status,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual("Updated Title", epic.title)

    def test_post_updates_epic_description(self):
        """POST updates the epic description."""
        epic = EpicFactory(project=self.project, description="Original description")

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": epic.status,
                "description": "Updated description",
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual("Updated description", epic.description)

    def test_post_updates_epic_status(self):
        """POST updates the epic status."""
        epic = EpicFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": IssueStatus.IN_PROGRESS,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, epic.status)

    def test_post_updates_epic_priority(self):
        """POST updates the epic priority."""
        epic = EpicFactory(project=self.project, priority=IssuePriority.LOW)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": epic.status,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, epic.priority)

    def test_post_updates_epic_assignee(self):
        """POST updates the epic assignee."""
        epic = EpicFactory(project=self.project, assignee=None)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": epic.status,
                "assignee": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual(self.user, epic.assignee)

    def test_post_updates_epic_milestone(self):
        """POST updates the epic milestone."""
        epic = EpicFactory(project=self.project, milestone=None)
        milestone = MilestoneFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": epic.status,
                "milestone": milestone.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        self.assertEqual(milestone, epic.milestone)

    def test_post_updates_epic_due_date(self):
        """POST updates the epic due date."""
        epic = EpicFactory(project=self.project, due_date=None)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": epic.title,
                "status": epic.status,
                "due_date": "2026-03-15",
            },
        )

        self.assertEqual(200, response.status_code)
        epic.refresh_from_db()
        from datetime import date

        self.assertEqual(date(2026, 3, 15), epic.due_date)

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        epic = EpicFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(epic),
            {
                "title": "",  # Required field
                "status": epic.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/epic_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)


class IssueDetailInlineEditViewTest(IssueViewTestBase):
    """Tests for the inline edit view for non-epic issue details page."""

    def _get_inline_edit_url(self, issue):
        return reverse(
            "issues:issue_detail_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_returns_edit_template(self):
        """GET request returns the edit template with form."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story))

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertIn("issue", response.context)

    def test_get_with_cancel_returns_display_template(self):
        """GET with cancel=1 returns the display template."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story) + "?cancel=1")

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_detail_header.html")

    def test_post_updates_issue_title(self):
        """POST updates the issue title."""
        story = StoryFactory(project=self.project, title="Original Title")

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": "Updated Title",
                "status": story.status,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual("Updated Title", story.title)

    def test_post_updates_issue_description(self):
        """POST updates the issue description."""
        story = StoryFactory(project=self.project, description="Original description")

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "description": "Updated description",
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual("Updated description", story.description)

    def test_post_updates_issue_status(self):
        """POST updates the issue status."""
        story = StoryFactory(project=self.project, status=IssueStatus.DRAFT)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": IssueStatus.IN_PROGRESS,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(IssueStatus.IN_PROGRESS, story.status)

    def test_post_updates_issue_priority(self):
        """POST updates the issue priority."""
        story = StoryFactory(project=self.project, priority=IssuePriority.LOW)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "priority": IssuePriority.HIGH,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(IssuePriority.HIGH, story.priority)

    def test_post_updates_issue_assignee(self):
        """POST updates the issue assignee."""
        story = StoryFactory(project=self.project, assignee=None)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "assignee": self.user.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(self.user, story.assignee)

    def test_post_updates_issue_due_date(self):
        """POST updates the issue due date."""
        story = StoryFactory(project=self.project, due_date=None)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "due_date": "2026-03-15",
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        from datetime import date

        self.assertEqual(date(2026, 3, 15), story.due_date)

    def test_post_updates_issue_estimated_points(self):
        """POST updates the issue estimated points."""
        story = StoryFactory(project=self.project, estimated_points=None)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "estimated_points": 5,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(5, story.estimated_points)

    def test_post_updates_issue_parent(self):
        """POST updates the issue parent (moves in tree)."""
        epic = EpicFactory(project=self.project)
        story = StoryFactory(project=self.project)  # No parent initially

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": story.title,
                "status": story.status,
                "parent": epic.pk,
            },
        )

        self.assertEqual(200, response.status_code)
        story.refresh_from_db()
        self.assertEqual(epic, story.get_parent())

    def test_post_updates_bug_severity(self):
        """POST updates the bug severity."""
        bug = BugFactory(project=self.project, severity=BugSeverity.MINOR)

        response = self.client.post(
            self._get_inline_edit_url(bug),
            {
                "title": bug.title,
                "status": bug.status,
                "severity": BugSeverity.CRITICAL,
            },
        )

        self.assertEqual(200, response.status_code)
        bug.refresh_from_db()
        self.assertEqual(BugSeverity.CRITICAL, bug.severity)

    def test_is_bug_context_for_bug(self):
        """is_bug context is True for bugs."""
        bug = BugFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(bug))

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.context["is_bug"])

    def test_is_bug_context_for_story(self):
        """is_bug context is False for stories."""
        story = StoryFactory(project=self.project)

        response = self.client.get(self._get_inline_edit_url(story))

        self.assertEqual(200, response.status_code)
        self.assertFalse(response.context["is_bug"])

    def test_post_with_validation_error_returns_edit_template(self):
        """POST with validation error returns edit template with errors."""
        story = StoryFactory(project=self.project)

        response = self.client.post(
            self._get_inline_edit_url(story),
            {
                "title": "",  # Required field
                "status": story.status,
            },
        )

        self.assertEqual(200, response.status_code)
        self.assertTemplateUsed(response, "issues/includes/issue_detail_header_edit.html")
        self.assertIn("form", response.context)
        self.assertTrue(response.context["form"].errors)
