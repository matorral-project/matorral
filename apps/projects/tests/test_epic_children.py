from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, MilestoneFactory, StoryFactory
from apps.issues.helpers import annotate_epic_child_counts, get_orphan_work_items
from apps.projects.factories import ProjectFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_MEMBER


class EpicChildCountsTest(TestCase):
    """Tests for annotate_epic_child_counts helper."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic1 = EpicFactory(project=cls.project, title="Epic 1")
        cls.epic2 = EpicFactory(project=cls.project, title="Epic 2")
        cls.epic_empty = EpicFactory(project=cls.project, title="Epic Empty")

        # Add children to epic1
        StoryFactory(project=cls.project, title="Story 1", parent=cls.epic1)
        BugFactory(project=cls.project, title="Bug 1", parent=cls.epic1)

        # Add one child to epic2
        StoryFactory(project=cls.project, title="Story 2", parent=cls.epic2)

    def test_child_counts_correct(self):
        epics = [self.epic1, self.epic2, self.epic_empty]
        annotate_epic_child_counts(epics)

        self.assertEqual(self.epic1.child_count, 2)
        self.assertEqual(self.epic2.child_count, 1)
        self.assertEqual(self.epic_empty.child_count, 0)

    def test_empty_list(self):
        annotate_epic_child_counts([])

    def test_single_epic_no_children(self):
        epics = [self.epic_empty]
        annotate_epic_child_counts(epics)
        self.assertEqual(self.epic_empty.child_count, 0)


class OrphanWorkItemsTest(TestCase):
    """Tests for get_orphan_work_items helper."""

    @classmethod
    def setUpTestData(cls):
        cls.project = ProjectFactory()
        cls.epic = EpicFactory(project=cls.project, title="Epic")

        # Children of epic (should NOT appear as orphans)
        StoryFactory(project=cls.project, title="Child Story", parent=cls.epic)

        # Root-level work items (orphans)
        cls.orphan_story = StoryFactory(project=cls.project, title="Orphan Story")
        cls.orphan_bug = BugFactory(project=cls.project, title="Orphan Bug")
        cls.orphan_chore = ChoreFactory(project=cls.project, title="Orphan Chore")

    def test_returns_only_root_work_items(self):
        orphans = get_orphan_work_items(self.project)
        orphan_keys = set(orphans.values_list("key", flat=True))

        self.assertIn(self.orphan_story.key, orphan_keys)
        self.assertIn(self.orphan_bug.key, orphan_keys)
        self.assertIn(self.orphan_chore.key, orphan_keys)
        # Epic should not be in orphans (it's an epic, not a work item)
        self.assertNotIn(self.epic.key, orphan_keys)

    def test_excludes_epic_children(self):
        orphans = get_orphan_work_items(self.project)
        orphan_titles = list(orphans.values_list("title", flat=True))
        self.assertNotIn("Child Story", orphan_titles)

    def test_search_filter(self):
        orphans = get_orphan_work_items(self.project, search_query="Bug")
        self.assertEqual(orphans.count(), 1)

    def test_status_filter(self):
        orphans = get_orphan_work_items(self.project, status_filter="in_progress")
        self.assertEqual(orphans.count(), 0)  # All are draft by default

    def test_empty_project(self):
        empty_project = ProjectFactory()
        orphans = get_orphan_work_items(empty_project)
        self.assertEqual(orphans.count(), 0)


class ProjectEpicChildrenViewTest(TestCase):
    """Tests for ProjectEpicChildrenView."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_MEMBER)
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.epic = EpicFactory(project=cls.project, title="Test Epic")
        cls.story = StoryFactory(project=cls.project, title="Child Story", parent=cls.epic)
        cls.bug = BugFactory(project=cls.project, title="Child Bug", parent=cls.epic)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_url(self):
        return reverse(
            "projects:project_epic_children",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": self.project.key,
                "epic_key": self.epic.key,
            },
        )

    def test_returns_children(self):
        response = self.client.get(self._get_url(), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Child Story")
        self.assertContains(response, "Child Bug")

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 302)


class EpicChildInlineEditTest(TestCase):
    """Tests for inline editing of epic child rows on the project detail page."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_MEMBER)
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.epic = EpicFactory(project=cls.project, title="Test Epic")
        cls.story = StoryFactory(project=cls.project, title="Child Story", parent=cls.epic)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _inline_edit_url(self, issue):
        return reverse(
            "issues:issue_inline_edit",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_get_edit_mode_returns_edit_template(self):
        url = self._inline_edit_url(self.story) + "?embed=project_epic_children&parent_key=" + self.epic.key
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="status"')
        # Verify it's a single <tr> with 7 <td> elements
        content = response.content.decode()
        self.assertEqual(content.count("<td"), 7)
        # Verify correct template
        template_names = [t.name for t in response.templates]
        self.assertIn("projects/includes/epic_children_row_edit_embed.html", template_names)
        # Verify hidden embed field is present
        self.assertContains(response, 'name="embed" value="project_epic_children"')

    def test_get_cancel_returns_display_template(self):
        url = (
            self._inline_edit_url(self.story) + "?embed=project_epic_children&parent_key=" + self.epic.key + "&cancel=1"
        )
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.story.title)
        # Verify it's a single <tr> with 7 <td> elements
        content = response.content.decode()
        self.assertEqual(content.count("<td"), 7)

    def test_post_save_returns_display_template_with_correct_columns(self):
        url = self._inline_edit_url(self.story) + "?embed=project_epic_children&parent_key=" + self.epic.key
        response = self.client.post(
            url,
            {
                "title": "Updated Title",
                "status": self.story.status,
                "priority": self.story.priority,
                "embed": "project_epic_children",
                "parent_key": self.epic.key,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updated Title")
        # Verify display row has exactly 7 <td> elements (matching the 7-column epic table)
        content = response.content.decode()
        self.assertEqual(
            content.count("<td"),
            7,
            f"Expected 7 <td> elements but got {content.count('<td')}. Response:\n{content[:500]}",
        )
        # Should NOT contain checkbox (those are for epic rows)
        self.assertNotContains(response, 'name="issues"')
        # Should contain the actions menu
        self.assertContains(response, "fa-ellipsis-vertical")

    def test_post_save_with_embed_only_in_query_string(self):
        """Verify POST works when embed is only in query string (not in POST body)."""
        url = self._inline_edit_url(self.story) + "?embed=project_epic_children&parent_key=" + self.epic.key
        response = self.client.post(
            url,
            {
                "title": "Updated Title QS Only",
                "status": self.story.status,
                "priority": self.story.priority,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updated Title QS Only")
        content = response.content.decode()
        self.assertEqual(
            content.count("<td"),
            7,
            f"Expected 7 <td> elements but got {content.count('<td')}. Response:\n{content[:500]}",
        )

    def test_post_save_with_embed_only_in_post_body(self):
        """Verify POST works when embed is only in POST body (HTMX hidden fields pattern)."""
        url = self._inline_edit_url(self.story)  # No query params!
        response = self.client.post(
            url,
            {
                "title": "Updated Title POST Only",
                "status": self.story.status,
                "priority": self.story.priority,
                "embed": "project_epic_children",
                "parent_key": self.epic.key,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Updated Title POST Only")
        content = response.content.decode()
        self.assertEqual(
            content.count("<td"),
            7,
            f"Expected 7 <td> elements but got {content.count('<td')}. Response:\n{content[:500]}",
        )
        # Verify correct template was used (should have x-show for Alpine.js)
        self.assertContains(response, "expandedEpics")
        # Should NOT have checkbox (those are for epic rows)
        self.assertNotContains(response, 'name="issues"')
        # Should contain the actions menu
        self.assertContains(response, "fa-ellipsis-vertical")

    def test_post_uses_correct_template(self):
        """Verify the correct template name is used in the response."""
        url = self._inline_edit_url(self.story)
        response = self.client.post(
            url,
            {
                "title": "Template Check",
                "status": self.story.status,
                "priority": self.story.priority,
                "embed": "project_epic_children",
                "parent_key": self.epic.key,
            },
            HTTP_HX_REQUEST="true",
        )
        template_names = [t.name for t in response.templates]
        self.assertIn("projects/includes/epic_child_row_embed.html", template_names)


class ProjectOrphanIssuesEmbedTest(TestCase):
    """Tests for ProjectOrphanIssuesEmbedView."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_MEMBER)
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.milestone = MilestoneFactory(project=cls.project, title="M1")
        cls.epic = EpicFactory(project=cls.project, title="Epic 1", milestone=cls.milestone)
        cls.orphan = StoryFactory(project=cls.project, title="Orphan Story")

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_url(self, project=None):
        project = project or self.project
        return reverse(
            "projects:project_orphan_issues_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": project.key,
            },
        )

    def test_context_includes_orphan_issues(self):
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("issues", response.context)
        issue_keys = [item.key for item in response.context["issues"]]
        self.assertIn(self.orphan.key, issue_keys)

    def test_orphans_visible_without_milestones_or_epics(self):
        """Orphan items should be shown even when the project has no milestones or epics."""
        project = ProjectFactory(workspace=self.workspace)
        orphan = StoryFactory(project=project, title="Lone Orphan")
        response = self.client.get(self._get_url(project=project))
        self.assertEqual(response.status_code, 200)
        issue_keys = [item.key for item in response.context["issues"]]
        self.assertIn(orphan.key, issue_keys)
        self.assertContains(response, orphan.key)

    def test_epics_not_in_orphan_list(self):
        """Epics should not appear in the orphan issues list."""
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        issue_keys = [item.key for item in response.context["issues"]]
        self.assertNotIn(self.epic.key, issue_keys)

    def test_search_filter(self):
        response = self.client.get(self._get_url(), {"search": "Orphan"})
        self.assertEqual(response.status_code, 200)
        issue_keys = [item.key for item in response.context["issues"]]
        self.assertIn(self.orphan.key, issue_keys)

    def test_context_has_project_orphan_flag(self):
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["project_orphan"])


class ProjectEpicsEmbedChildCountTest(TestCase):
    """Tests for epic child counts in ProjectEpicsEmbedView."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_MEMBER)
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.milestone = MilestoneFactory(project=cls.project, title="M1")
        cls.epic = EpicFactory(project=cls.project, title="Epic 1", milestone=cls.milestone)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_epics_have_child_count(self):
        StoryFactory(project=self.project, title="Epic Child", parent=self.epic)
        url = reverse(
            "projects:project_epics_embed",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": self.project.key,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        grouped_epics = response.context["grouped_epics"]
        for group in grouped_epics:
            for epic in group["epics"]:
                if epic.key == self.epic.key:
                    self.assertEqual(epic.child_count, 1)
                    return
        self.fail("Epic not found in grouped_epics")
