from functools import wraps

from django.http import Http404, HttpResponseRedirect
from django.urls import reverse


def login_and_workspace_membership_required(view_func):
    """Require user to be logged in and a member of the workspace."""
    return _get_decorated_function(view_func, require_admin=False)


def workspace_admin_required(view_func):
    """Require user to be logged in and an admin of the workspace."""
    return _get_decorated_function(view_func, require_admin=True)


def _get_decorated_function(view_func, require_admin=False):
    @wraps(view_func)
    def _inner(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return HttpResponseRedirect("{}?next={}".format(reverse("account_login"), request.path))

        workspace = request.workspace  # set by WorkspacesMiddleware
        membership = request.workspace_membership  # set by WorkspacesMiddleware

        # Check membership (and admin role if required)
        has_permission = membership and (not require_admin or membership.is_admin())

        if not workspace or not has_permission:
            raise Http404

        return view_func(request, *args, **kwargs)

    return _inner
