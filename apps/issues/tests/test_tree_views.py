from django.test import Client, TestCase
from django.urls import reverse

from apps.issues.factories import EpicFactory
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
