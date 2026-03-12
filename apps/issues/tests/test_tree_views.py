from django.contrib.sites.models import Site
from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory, StoryFactory
from apps.projects.factories import ProjectFactory
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


class IssueMoveViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get_move_url(self, issue):
        return reverse(
            "issues:issue_move",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

    def test_moving_epic_under_parent_returns_400(self):
        """Epics cannot have a parent; non-HTMX POST returns JSON 400."""
        epic = EpicFactory(project=self.project)
        other_epic = EpicFactory(project=self.project)

        response = self.client.post(self._get_move_url(epic), {"parent_key": other_epic.key})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("Epics cannot have a parent issue", data["error"])

    def test_moving_epic_under_parent_with_htmx_renders_messages(self):
        """HTMX variant: same validation, but returns 200 with messages partial."""
        epic = EpicFactory(project=self.project)
        other_epic = EpicFactory(project=self.project)

        response = self.client.post(
            self._get_move_url(epic),
            {"parent_key": other_epic.key},
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "includes/messages.html")


class IssueChildrenViewTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)
        cls.epic = EpicFactory(project=cls.project)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        Site.objects.get_current()  # warm up cache for stable query count
        # Create children with assignees in setUp so they don't affect other tests
        for assignee in UserFactory.create_batch(3):
            StoryFactory(project=self.project, parent=self.epic, assignee=assignee)

    def _get_url(self):
        return reverse(
            "issues:issue_children",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": self.epic.key,
            },
        )

    def test_returns_children(self):
        response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["children"]), 3)

    def test_children_query_count(self):
        """Verify no N+1 queries when loading children with assignees.

        Query breakdown (16 total, constant regardless of child count):
          session(1) + user auth(1) + workspace(1) + project+membership(2)
          + epic base+polymorphic(2) + onboarding ctx(5)
          + children base query with JOINs(1) + children polymorphic(1)
          + session save(2) + savepoint(1)
        django_site is pre-warmed in setUp to ensure consistent count across test orderings.
        """
        with self.assertNumQueries(16):
            response = self.client.get(self._get_url())
        self.assertEqual(response.status_code, 200)
