from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from apps.sprints.factories import SprintFactory
from apps.sprints.forms import SprintBulkOwnerForm
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.registry import (
    ActionType,
    BaseAction,
    SprintAction,
    SprintActionRegistry,
    SprintBulkAction,
    SprintBulkActionRegistry,
    sprint_actions,
    sprint_bulk_actions,
)
from apps.users.factories import UserFactory
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN


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


class BaseActionInheritanceTest(TestCase):
    """Tests that SprintAction and SprintBulkAction both inherit BaseAction."""

    def test_sprint_action_inherits_base_action(self):
        self.assertTrue(issubclass(SprintAction, BaseAction))

    def test_sprint_bulk_action_inherits_base_action(self):
        self.assertTrue(issubclass(SprintBulkAction, BaseAction))

    def test_base_action_has_expected_fields(self):
        action = BaseAction()

        self.assertEqual("", action.name)
        self.assertEqual("", action.label)
        self.assertEqual("", action.icon)
        self.assertFalse(action.confirm)
        self.assertEqual("btn-primary", action.css_class)


class SprintBulkActionRegistryTest(TestCase):
    """Unit tests for SprintBulkActionRegistry."""

    def test_register_and_get_roundtrip(self):
        """Registering a bulk action class and retrieving it by name works."""
        registry = SprintBulkActionRegistry()

        class FooBulkAction(SprintBulkAction):
            name = "foo-bulk"
            label = "Foo Bulk"
            icon = "star"

            def execute(self, queryset, request):
                return "done"

        registry.register(FooBulkAction)
        result = registry.get("foo-bulk")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, FooBulkAction)
        self.assertEqual("foo-bulk", result.name)

    def test_register_instance(self):
        """register_instance() registers a pre-built instance."""
        registry = SprintBulkActionRegistry()
        instance = SprintBulkAction()
        instance.name = "custom"
        registry.register_instance(instance)

        self.assertIs(instance, registry.get("custom"))

    def test_get_unknown_name_returns_none(self):
        """Getting an unregistered action name returns None."""
        registry = SprintBulkActionRegistry()

        self.assertIsNone(registry.get("unknown"))

    def test_all_returns_all_registered_actions(self):
        """all() returns all registered bulk actions."""
        registry = SprintBulkActionRegistry()

        class A(SprintBulkAction):
            name = "a"

            def execute(self, queryset, request):
                return "a"

        class B(SprintBulkAction):
            name = "b"

            def execute(self, queryset, request):
                return "b"

        registry.register(A)
        registry.register(B)

        names = [a.name for a in registry.all()]
        self.assertEqual(["a", "b"], names)


class BulkDeleteActionTest(TestCase):
    """Tests for BulkDeleteAction."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def test_execute_deletes_sprints(self):
        sprint1 = SprintFactory(workspace=self.workspace)
        sprint2 = SprintFactory(workspace=self.workspace)
        SprintFactory(workspace=self.workspace)

        action = sprint_bulk_actions.get("delete")
        queryset = Sprint.objects.filter(pk__in=[sprint1.pk, sprint2.pk])

        request = RequestFactory().post("/")
        request.workspace = self.workspace

        deleted_count, remaining_count = action.execute(queryset, request)

        self.assertEqual(2, deleted_count)
        self.assertEqual(1, remaining_count)

    def test_confirm_is_true(self):
        action = sprint_bulk_actions.get("delete")

        self.assertTrue(action.confirm)

    def test_render_type_is_menu(self):
        action = sprint_bulk_actions.get("delete")

        self.assertEqual("menu", action.render_type)


class BulkStatusActionTest(TestCase):
    """Tests for BulkStatusAction."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def test_registered_for_each_status(self):
        for value, _label in SprintStatus.choices:
            action = sprint_bulk_actions.get(f"status-{value}")
            self.assertIsNotNone(action, f"No bulk action registered for status-{value}")

    def test_validate_rejects_multi_select_for_active(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.ACTIVE}")
        sprint1 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        sprint2 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        queryset = Sprint.objects.filter(pk__in=[sprint1.pk, sprint2.pk])

        with self.assertRaises(ValidationError):
            action.validate(queryset, None)

    def test_validate_allows_single_select_for_active(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.ACTIVE}")
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        queryset = Sprint.objects.filter(pk=sprint.pk)

        # Should not raise
        action.validate(queryset, None)

    def test_execute_updates_status_bulk(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.ARCHIVED}")
        sprint1 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)
        sprint2 = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        queryset = Sprint.objects.filter(pk__in=[sprint1.pk, sprint2.pk])
        request = RequestFactory().post("/")
        request.workspace = self.workspace
        request.user = self.user

        result = action.execute(queryset, request)

        sprint1.refresh_from_db()
        sprint2.refresh_from_db()
        self.assertEqual(SprintStatus.ARCHIVED, sprint1.status)
        self.assertEqual(SprintStatus.ARCHIVED, sprint2.status)
        self.assertIn("2", str(result))

    def test_execute_active_calls_start(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.ACTIVE}")
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        queryset = Sprint.objects.filter(pk=sprint.pk)
        request = RequestFactory().post("/")
        request.workspace = self.workspace
        request.user = self.user

        result = action.execute(queryset, request)

        sprint.refresh_from_db()
        self.assertEqual(SprintStatus.ACTIVE, sprint.status)
        self.assertIn(sprint.name, str(result))

    def test_execute_active_raises_on_start_error(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.ACTIVE}")
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.PLANNING)

        queryset = Sprint.objects.filter(pk=sprint.pk)
        request = RequestFactory().post("/")
        request.workspace = self.workspace
        request.user = self.user

        with (
            patch.object(Sprint, "start", side_effect=ValueError("Cannot start")),
            self.assertRaises(ValidationError),
        ):
            action.execute(queryset, request)

    def test_render_type_is_dropdown(self):
        action = sprint_bulk_actions.get(f"status-{SprintStatus.PLANNING}")

        self.assertEqual("dropdown", action.render_type)


class BulkOwnerActionTest(TestCase):
    """Tests for BulkOwnerAction."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()
        cls.user = UserFactory()
        MembershipFactory(workspace=cls.workspace, user=cls.user, role=ROLE_ADMIN)

    def test_get_form_class_returns_form(self):
        action = sprint_bulk_actions.get("owner")
        form_class = action.get_form_class()

        self.assertEqual(SprintBulkOwnerForm, form_class)

    def test_render_type_is_modal(self):
        action = sprint_bulk_actions.get("owner")

        self.assertEqual("modal", action.render_type)
