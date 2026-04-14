from dataclasses import dataclass

from django.test import SimpleTestCase

from apps.generic_ui.actions import (
    Action,
    ActionRegistry,
    ActionType,
    BaseAction,
    BoundAction,
    BulkAction,
    BulkActionResult,
    RenderType,
)


@dataclass
class StubSubject:
    """Minimal subject used by action tests."""

    pk: int = 1
    name: str = "stub"


def _make_action(
    action_name="foo",
    *,
    available=True,
    action_type=ActionType.PRIMARY,
    url="/foo/",
    confirm_url="/foo/confirm/",
):
    class FooAction(Action):
        name = action_name
        label = "Foo"
        icon = "star"

        def is_available(self, subject, user):
            return available

        def execute(self, subject, request):
            return "executed"

        def get_url(self, subject):
            return url

        def get_confirm_url(self, subject):
            return confirm_url

    FooAction.action_type = action_type

    return FooAction


class BaseActionFieldsTest(SimpleTestCase):
    def test_default_fields(self):
        action = BaseAction()

        self.assertEqual("", action.name)
        self.assertEqual("", action.label)
        self.assertEqual("", action.icon)
        self.assertFalse(action.confirm)
        self.assertEqual("btn-primary", action.css_class)

    def test_action_inherits_base_action(self):
        self.assertTrue(issubclass(Action, BaseAction))

    def test_bulk_action_inherits_base_action(self):
        self.assertTrue(issubclass(BulkAction, BaseAction))


class RenderTypeEnumTest(SimpleTestCase):
    def test_values(self):
        self.assertEqual("button", RenderType.BUTTON)
        self.assertEqual("dropdown", RenderType.DROPDOWN)
        self.assertEqual("modal", RenderType.MODAL)
        self.assertEqual("menu", RenderType.MENU)

    def test_is_str_enum(self):
        self.assertEqual("button", str(RenderType.BUTTON.value))


class BulkActionResultTest(SimpleTestCase):
    def test_message_only(self):
        result = BulkActionResult(message="done")

        self.assertEqual("done", result.message)
        self.assertIsNone(result.remaining_count)

    def test_with_remaining_count(self):
        result = BulkActionResult(message="done", remaining_count=5)

        self.assertEqual(5, result.remaining_count)


class ActionRegistryRegistrationTest(SimpleTestCase):
    def test_register_and_get_roundtrip(self):
        registry = ActionRegistry[Action]()
        cls = _make_action()

        registry.register(cls)
        result = registry.get("foo")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, cls)
        self.assertEqual("foo", result.name)

    def test_get_unknown_name_returns_none(self):
        registry = ActionRegistry[Action]()

        self.assertIsNone(registry.get("unknown"))

    def test_register_instance(self):
        registry = ActionRegistry[BulkAction]()
        instance = BulkAction()
        instance.name = "custom"

        registry.register_instance(instance)

        self.assertIs(instance, registry.get("custom"))

    def test_all_returns_all_registered_actions(self):
        registry = ActionRegistry[Action]()
        registry.register(_make_action("a"))
        registry.register(_make_action("b"))

        names = [a.name for a in registry.all()]

        self.assertEqual(["a", "b"], names)


class ActionRegistryFilteringTest(SimpleTestCase):
    def test_available_for_filters_by_is_available(self):
        registry = ActionRegistry[Action]()
        registry.register(_make_action("always", available=True))
        registry.register(_make_action("never", available=False))

        available = registry.available_for(StubSubject(), user=None)
        names = [a.name for a in available]

        self.assertIn("always", names)
        self.assertNotIn("never", names)

    def test_primary_for_filters_by_action_type(self):
        registry = ActionRegistry[Action]()
        registry.register(_make_action("p", action_type=ActionType.PRIMARY))
        registry.register(_make_action("m", action_type=ActionType.MENU))

        primary = registry.primary_for(StubSubject(), user=None)

        self.assertEqual(["p"], [a.name for a in primary])
        for action in primary:
            self.assertEqual(ActionType.PRIMARY, action.action_type)

    def test_menu_for_filters_by_action_type(self):
        registry = ActionRegistry[Action]()
        registry.register(_make_action("p", action_type=ActionType.PRIMARY))
        registry.register(_make_action("m", action_type=ActionType.MENU))

        menu = registry.menu_for(StubSubject(), user=None)

        self.assertEqual(["m"], [a.name for a in menu])
        for action in menu:
            self.assertEqual(ActionType.MENU, action.action_type)

    def test_primary_for_skips_unavailable(self):
        registry = ActionRegistry[Action]()
        registry.register(_make_action("p", action_type=ActionType.PRIMARY, available=False))

        self.assertEqual([], registry.primary_for(StubSubject(), user=None))


class BoundActionFactoryTest(SimpleTestCase):
    def test_from_action_copies_fields(self):
        cls = _make_action(url="/x/", confirm_url="/x/confirm/")
        action = cls()
        action.confirm = True
        action.confirm_title = "Confirm?"
        action.confirm_body = "Really?"
        action.css_class = "btn-danger"
        subject = StubSubject()

        bound = BoundAction.from_action(action, subject)

        self.assertEqual("foo", bound.name)
        self.assertEqual("Foo", bound.label)
        self.assertEqual("star", bound.icon)
        self.assertEqual("btn-danger", bound.css_class)
        self.assertTrue(bound.confirm)
        self.assertEqual("/x/", bound.url)
        self.assertEqual("/x/confirm/", bound.confirm_url)
        self.assertEqual("Confirm?", bound.confirm_title)
        self.assertEqual("Really?", bound.confirm_body)
        self.assertEqual(RenderType.BUTTON, bound.render_type)

    def test_from_action_reads_render_type_when_present(self):
        class FooBulk(BulkAction):
            name = "foo"
            label = "Foo"
            icon = "star"
            render_type = RenderType.MODAL

            def execute(self, queryset, request, extra_cleaned_data=None):
                return BulkActionResult(message="ok")

            def get_url(self, workspace):
                return "/bulk/"

            def get_confirm_url(self, workspace):
                return "/bulk/confirm/"

        bound = BoundAction.from_action(FooBulk(), StubSubject())

        self.assertEqual(RenderType.MODAL, bound.render_type)

    def test_from_action_defaults_render_type_when_missing(self):
        class NoRenderType:
            name = "foo"
            label = "Foo"
            icon = "star"
            css_class = "btn-primary"
            confirm = False
            confirm_title = ""
            confirm_body = ""

            def get_url(self, subject):
                return "/u/"

            def get_confirm_url(self, subject):
                return "/c/"

        bound = BoundAction.from_action(NoRenderType(), StubSubject())

        self.assertEqual(RenderType.BUTTON, bound.render_type)
