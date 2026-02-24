from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage import default_storage
from django.contrib.sessions.backends.file import SessionStore
from django.test import RequestFactory

from apps.workspaces.middleware import WorkspacesMiddleware


def create_test_request(
    path="/",
    user=None,
    method="get",
    with_messages=False,
    with_session=True,
    htmx=False,
):
    """
    Create a mock request for testing views.

    Args:
        path: URL path for the request (default: "/")
        user: User instance or None for AnonymousUser
        method: HTTP method - "get" or "post" (default: "get")
        with_messages: If True, attach Django messages storage
        with_session: If True, attach a session (SessionStore if with_messages, else empty dict)
        htmx: Value for request.htmx attribute (default: False)

    Returns:
        A mock request object suitable for passing to views.
    """
    factory = RequestFactory()
    request = factory.post(path) if method.lower() == "post" else factory.get(path)
    request.user = user or AnonymousUser()
    request.htmx = htmx

    if with_session:
        if with_messages:
            request.session = SessionStore()
        else:
            request.session = {}

    if with_messages:
        request._messages = default_storage(request)

    return request


def call_view_with_middleware(view_cls, user, workspace_slug=None, path="/", **view_kwargs):
    """
    Call a view through WorkspacesMiddleware for testing workspace-based access control.

    Args:
        view_cls: The view class to test
        user: User instance (or AnonymousUser)
        workspace_slug: The workspace slug to include in view kwargs
        path: URL path for the request (default: "/")
        **view_kwargs: Additional kwargs to pass to the view

    Returns:
        The response from the view.
    """
    request = create_test_request(path=path, user=user)
    all_view_kwargs = view_kwargs
    if workspace_slug:
        all_view_kwargs = {"workspace_slug": workspace_slug, **view_kwargs}

    def get_response(req):
        return view_cls.as_view()(req, **all_view_kwargs)

    middleware = WorkspacesMiddleware(get_response=get_response)
    middleware.process_view(request, None, None, all_view_kwargs)
    return middleware(request)
