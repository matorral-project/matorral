from django.test import TestCase

from apps.sprints.factories import SprintFactory
from apps.sprints.models import SprintStatus
from apps.sprints.registry import (
    ActionType,
    SprintAction,
    SprintActionRegistry,
    sprint_actions,
)
from apps.users.factories import UserFactory
from apps.workspaces.factories import WorkspaceFactory


class SprintActionRegistryTest(TestCase):
    """Unit tests for SprintActionRegistry."""

    def test_register_and_get_roundtrip(self):
        """Registering an action class and retrieving it by name works."""
        registry = SprintActionRegistry()

        class FooAction(SprintAction):
            name = "foo"
            label = "Foo"
            icon = "star"
            action_type = ActionType.PRIMARY

            def is_available(self, sprint, user):
                return True

            def execute(self, sprint, request):
                pass

        registry.register(FooAction)
        result = registry.get("foo")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, FooAction)
        self.assertEqual("foo", result.name)

    def test_get_unknown_name_returns_none(self):
        """Getting an unregistered action name returns None."""
        registry = SprintActionRegistry()

        self.assertIsNone(registry.get("unknown"))

    def test_available_for_filters_by_is_available(self):
        """available_for() only returns actions where is_available() is True."""
        registry = SprintActionRegistry()

        class AlwaysAvailable(SprintAction):
            name = "always"
            label = "Always"
            icon = "check"
            action_type = ActionType.PRIMARY

            def is_available(self, sprint, user):
                return True

            def execute(self, sprint, request):
                pass

        class NeverAvailable(SprintAction):
            name = "never"
            label = "Never"
            icon = "x"
            action_type = ActionType.MENU

            def is_available(self, sprint, user):
                return False

            def execute(self, sprint, request):
                pass

        registry.register(AlwaysAvailable)
        registry.register(NeverAvailable)

        workspace = WorkspaceFactory()
        sprint = SprintFactory(workspace=workspace)
        user = UserFactory()
        available = registry.available_for(sprint, user)

        names = [a.name for a in available]
        self.assertIn("always", names)
        self.assertNotIn("never", names)

    def test_primary_for_filters_by_action_type(self):
        """primary_for() returns only PRIMARY actions that are available."""
        workspace = WorkspaceFactory()
        sprint = SprintFactory(workspace=workspace, status=SprintStatus.PLANNING)
        user = UserFactory()

        primary = sprint_actions.primary_for(sprint, user)

        for action in primary:
            self.assertEqual(ActionType.PRIMARY, action.action_type)

    def test_menu_for_filters_by_action_type(self):
        """menu_for() returns only MENU actions that are available."""
        workspace = WorkspaceFactory()
        sprint = SprintFactory(workspace=workspace, status=SprintStatus.PLANNING)
        user = UserFactory()

        menu = sprint_actions.menu_for(sprint, user)

        for action in menu:
            self.assertEqual(ActionType.MENU, action.action_type)


class StartSprintActionIsAvailableTest(TestCase):
    """Tests for StartSprintAction.is_available()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()

    def test_available_for_planning(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        action = sprint_actions.get("start")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_not_available_for_active(self):
        sprint = SprintFactory(workspace=self.workspace, active=True)
        action = sprint_actions.get("start")

        self.assertFalse(action.is_available(sprint, self.user))

    def test_not_available_for_completed(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        action = sprint_actions.get("start")

        self.assertFalse(action.is_available(sprint, self.user))

    def test_not_available_for_archived(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)
        action = sprint_actions.get("start")

        self.assertFalse(action.is_available(sprint, self.user))


class CompleteSprintActionIsAvailableTest(TestCase):
    """Tests for CompleteSprintAction.is_available()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()

    def test_available_for_active(self):
        sprint = SprintFactory(workspace=self.workspace, active=True)
        action = sprint_actions.get("complete")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_not_available_for_planning(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        action = sprint_actions.get("complete")

        self.assertFalse(action.is_available(sprint, self.user))

    def test_not_available_for_completed(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        action = sprint_actions.get("complete")

        self.assertFalse(action.is_available(sprint, self.user))

    def test_not_available_for_archived(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)
        action = sprint_actions.get("complete")

        self.assertFalse(action.is_available(sprint, self.user))


class ArchiveSprintActionIsAvailableTest(TestCase):
    """Tests for ArchiveSprintAction.is_available()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()

    def test_available_for_planning(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        action = sprint_actions.get("archive")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_available_for_completed(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        action = sprint_actions.get("archive")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_not_available_for_active(self):
        sprint = SprintFactory(workspace=self.workspace, active=True)
        action = sprint_actions.get("archive")

        self.assertFalse(action.is_available(sprint, self.user))

    def test_not_available_for_archived(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)
        action = sprint_actions.get("archive")

        self.assertFalse(action.is_available(sprint, self.user))


class DeleteSprintActionIsAvailableTest(TestCase):
    """Tests for DeleteSprintAction.is_available()."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()

    def test_available_for_planning(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        action = sprint_actions.get("delete")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_available_for_active(self):
        sprint = SprintFactory(workspace=self.workspace, active=True)
        action = sprint_actions.get("delete")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_available_for_completed(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.COMPLETED)
        action = sprint_actions.get("delete")

        self.assertTrue(action.is_available(sprint, self.user))

    def test_available_for_archived(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ARCHIVED)
        action = sprint_actions.get("delete")

        self.assertTrue(action.is_available(sprint, self.user))
