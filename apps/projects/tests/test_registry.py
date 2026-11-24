from django.test import TestCase

from apps.generic_ui.actions import ActionType
from apps.projects.factories import ProjectFactory
from apps.projects.models import ProjectStatus
from apps.projects.registry import project_actions
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory


class SingleActionRegistrationTest(TestCase):
    """All single-project actions are registered under their expected names."""

    def test_all_actions_registered(self):
        for name in ["start", "complete", "reopen", "archive", "clone", "move", "delete"]:
            self.assertIsNotNone(project_actions.get(name), f"Action '{name}' is not registered")

    def test_action_types(self):
        primary = {"start", "complete", "reopen"}
        menu = {"archive", "clone", "move", "delete"}

        for name in primary:
            self.assertEqual(ActionType.PRIMARY, project_actions.get(name).action_type)
        for name in menu:
            self.assertEqual(ActionType.MENU, project_actions.get(name).action_type)

    def test_confirm_flags(self):
        for name in ["start", "complete", "reopen", "archive", "move", "delete"]:
            self.assertTrue(project_actions.get(name).confirm, f"Action '{name}' should require confirmation")
        self.assertFalse(project_actions.get("clone").confirm)


class StatusActionAvailabilityTest(TestCase):
    """is_available() matrix for status transition actions."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()

    def _project(self, status):
        return ProjectFactory(workspace=self.workspace, status=status)

    def test_start_available_only_for_draft(self):
        action = project_actions.get("start")
        self.assertTrue(action.is_available(self._project(ProjectStatus.DRAFT), self.user))
        for status in [ProjectStatus.ACTIVE, ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED]:
            self.assertFalse(action.is_available(self._project(status), self.user), f"start available for {status}")

    def test_complete_available_only_for_active(self):
        action = project_actions.get("complete")
        self.assertTrue(action.is_available(self._project(ProjectStatus.ACTIVE), self.user))
        for status in [ProjectStatus.DRAFT, ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED]:
            self.assertFalse(action.is_available(self._project(status), self.user), f"complete available for {status}")

    def test_reopen_available_for_completed_and_archived(self):
        action = project_actions.get("reopen")
        for status in [ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED]:
            self.assertTrue(action.is_available(self._project(status), self.user), f"reopen unavailable for {status}")
        for status in [ProjectStatus.DRAFT, ProjectStatus.ACTIVE]:
            self.assertFalse(action.is_available(self._project(status), self.user), f"reopen available for {status}")

    def test_archive_available_for_any_status_except_archived(self):
        action = project_actions.get("archive")
        for status in [ProjectStatus.DRAFT, ProjectStatus.ACTIVE, ProjectStatus.COMPLETED]:
            self.assertTrue(action.is_available(self._project(status), self.user), f"archive unavailable for {status}")
        self.assertFalse(action.is_available(self._project(ProjectStatus.ARCHIVED), self.user))


class CloneDeleteActionAvailabilityTest(TestCase):
    """Clone and delete are always available."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        cls.project = ProjectFactory(workspace=cls.workspace)

    def test_clone_always_available(self):
        for status, _label in ProjectStatus.choices:
            self.project.status = status
            self.assertTrue(project_actions.get("clone").is_available(self.project, self.user))

    def test_delete_always_available(self):
        for status, _label in ProjectStatus.choices:
            self.project.status = status
            self.assertTrue(project_actions.get("delete").is_available(self.project, self.user))


class MoveActionAvailabilityTest(TestCase):
    """Move requires at least one other workspace the user belongs to."""

    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.user = UserFactory()
        self.project = ProjectFactory(workspace=self.workspace)

    def test_not_available_without_other_workspaces(self):
        MembershipFactory(workspace=self.workspace, user=self.user)

        self.assertFalse(project_actions.get("move").is_available(self.project, self.user))

    def test_available_when_user_has_other_workspace(self):
        MembershipFactory(workspace=self.workspace, user=self.user)
        other_workspace = WorkspaceFactory()
        MembershipFactory(workspace=other_workspace, user=self.user)

        self.assertTrue(project_actions.get("move").is_available(self.project, self.user))
