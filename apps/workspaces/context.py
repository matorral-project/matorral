import contextlib
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

import sentry_sdk

if TYPE_CHECKING:
    from apps.workspaces.models import Workspace

_context: ContextVar[Workspace | None] = ContextVar("workspace", default=None)


class EmptyWorkspaceContextException(Exception):
    pass


def get_current_workspace() -> Workspace | None:
    """
    Get the workspace set in the current thread/context via `set_current_workspace`.
    Returns None if no workspace is set.
    """
    with contextlib.suppress(LookupError):
        return _context.get()
    return None


def set_current_workspace(workspace: Workspace | None) -> Token:
    """
    Set a workspace in the current thread/context.
    Used in middleware once a user is logged in.
    """
    workspace = _unwrap_lazy(workspace)
    token = _context.set(workspace)
    if workspace and hasattr(workspace, "slug"):
        sentry_sdk.get_current_scope().set_tag("workspace", workspace.slug)
    else:
        sentry_sdk.get_current_scope().remove_tag("workspace")
    return token


def unset_current_workspace(token: Token | None = None):
    """
    Reset the workspace context. If a token is provided, restore the previous value.
    """
    if token is None:
        _context.set(None)
        sentry_sdk.get_current_scope().remove_tag("workspace")
    else:
        _context.reset(token)
        if (workspace := get_current_workspace()) and hasattr(workspace, "slug"):
            sentry_sdk.get_current_scope().set_tag("workspace", workspace.slug)
        else:
            sentry_sdk.get_current_scope().remove_tag("workspace")


@contextmanager
def current_workspace(workspace: Workspace | None):
    """Context manager for setting the workspace outside requests."""
    token = set_current_workspace(workspace)
    try:
        yield
    finally:
        unset_current_workspace(token)


def _unwrap_lazy(obj):
    """Unwraps a lazy object if it is one, otherwise returns the object itself."""
    from django.utils.functional import LazyObject, empty

    if isinstance(obj, LazyObject):
        if obj._wrapped is empty:
            obj._setup()
        return obj._wrapped
    return obj
