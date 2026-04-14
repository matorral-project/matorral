"""Subject-agnostic action registry primitives.

This module provides the building blocks for registering and dispatching
user-facing actions (both single-object and bulk) across different domain
models. Consumers (e.g. ``apps.sprints``, ``apps.projects``) build on these
primitives to expose per-model action toolbars and detail-page buttons.

Recipe for adding a new consumer:

1. Subclass :class:`Action` and/or :class:`BulkAction` in
   ``apps/<app>/registry.py``, implementing ``execute()``, ``get_url()`` and
   ``get_confirm_url()``, plus (optionally) ``is_available``, ``validate`` and
   ``get_form_class``.
2. Instantiate an :class:`ActionRegistry` singleton
   (``foo_actions = ActionRegistry[Foo]()``) and register instances via
   ``@foo_actions.register`` or ``foo_actions.register_instance(...)``.
3. Wire dispatch by subclassing the generic view mixins — provide
   ``registry``, ``model`` and ``get_subject()`` — then add routes under an
   ``actions/<str:action_name>/`` prefix in ``urls.py`` and include the
   toolbar partial in templates.
"""

from dataclasses import dataclass
from enum import Enum, StrEnum


class ActionType(Enum):
    PRIMARY = "primary"
    MENU = "menu"


class RenderType(StrEnum):
    BUTTON = "button"
    DROPDOWN = "dropdown"
    MODAL = "modal"
    MENU = "menu"


@dataclass
class BulkActionResult:
    message: str
    remaining_count: int | None = None


class BaseAction:
    """Shared fields for single-subject and bulk actions."""

    name = ""
    label = ""
    icon = ""
    confirm = False
    confirm_title = ""
    confirm_body = ""
    css_class = "btn-primary"


class Action(BaseAction):
    """Action that operates on a single subject (detail page).

    Concrete subclasses must implement ``is_available``, ``execute``,
    ``get_url`` and ``get_confirm_url``. Override ``get_confirm_response``
    to customize the confirmation modal rendering.
    """

    action_type = ActionType.PRIMARY

    def is_available(self, subject, user) -> bool:
        raise NotImplementedError

    def execute(self, subject, request):
        raise NotImplementedError

    def get_url(self, subject) -> str:
        raise NotImplementedError

    def get_confirm_url(self, subject) -> str:
        raise NotImplementedError

    def get_confirm_response(self, subject, request):
        raise NotImplementedError


class BulkAction(BaseAction):
    """Action that operates on a queryset of subjects (list page toolbar)."""

    render_type: RenderType = RenderType.BUTTON
    modal_var: str = ""

    def validate(self, queryset, request):
        """Raise ValidationError to abort with user-facing message."""

    def execute(self, queryset, request, extra_cleaned_data: dict | None = None) -> BulkActionResult:
        """Perform the bulk operation. Return a :class:`BulkActionResult`.

        ``extra_cleaned_data`` holds the validated cleaned_data from the
        action's extra form (see :meth:`get_form_class`) when one is
        configured; otherwise ``None``.
        """
        raise NotImplementedError

    def get_form_class(self) -> type | None:
        """Override to provide extra form fields. Return None for no extra form."""
        return None

    def get_url(self, workspace) -> str:
        raise NotImplementedError

    def get_confirm_url(self, workspace) -> str:
        raise NotImplementedError


class ActionRegistry[T: BaseAction]:
    """Generic registry for action instances keyed by name.

    ``available_for``, ``primary_for`` and ``menu_for`` are intended for
    single-subject :class:`Action` registries — they require registered
    actions to expose ``is_available`` and ``action_type``.
    """

    def __init__(self):
        self._actions: dict[str, T] = {}

    def register(self, action_class: type[T]) -> type[T]:
        """Register an action class. Can be used as @decorator."""
        instance = action_class()
        self._actions[instance.name] = instance
        return action_class

    def register_instance(self, instance: T) -> None:
        """Register a pre-built action instance (for parameterized actions)."""
        self._actions[instance.name] = instance

    def get(self, name: str) -> T | None:
        return self._actions.get(name)

    def all(self) -> list[T]:
        return list(self._actions.values())

    def available_for(self, subject, user) -> list[T]:
        return [a for a in self._actions.values() if a.is_available(subject, user)]

    def primary_for(self, subject, user) -> list[T]:
        return [a for a in self.available_for(subject, user) if a.action_type == ActionType.PRIMARY]

    def menu_for(self, subject, user) -> list[T]:
        return [a for a in self.available_for(subject, user) if a.action_type == ActionType.MENU]


@dataclass
class BoundAction:
    name: str
    label: str
    icon: str
    css_class: str
    confirm: bool
    url: str
    confirm_url: str
    confirm_title: str = ""
    confirm_body: str = ""
    render_type: RenderType = RenderType.BUTTON
    modal_var: str = ""

    @classmethod
    def from_action(cls, action, subject) -> BoundAction:
        return cls(
            name=action.name,
            label=str(action.label),
            icon=action.icon,
            css_class=action.css_class,
            confirm=action.confirm,
            url=action.get_url(subject),
            confirm_url=action.get_confirm_url(subject),
            confirm_title=str(action.confirm_title),
            confirm_body=str(action.confirm_body),
            render_type=getattr(action, "render_type", RenderType.BUTTON),
            modal_var=getattr(action, "modal_var", ""),
        )


def build_bulk_action_context(registry: ActionRegistry, subject) -> dict:
    """Build the context dict consumed by `generic_ui/_bulk_toolbar.html`.

    Returns ``bulk_actions`` plus ``bulk_has_dropdown`` / ``bulk_has_menu``
    precomputed so the partial can conditionally render the grouped wrappers
    without iterating twice.
    """
    actions = [BoundAction.from_action(a, subject) for a in registry.all()]
    return {
        "bulk_actions": actions,
        "bulk_has_dropdown": any(a.render_type == RenderType.DROPDOWN for a in actions),
        "bulk_has_menu": any(a.render_type == RenderType.MENU for a in actions),
    }
