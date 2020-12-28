from django.http import Http404

from .models import Workspace


class WorkspaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.

        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_anonymous:
            return

        try:
            workspace_slug = view_kwargs['workspace']
        except KeyError:
            return None

        queryset = (Workspace.objects.filter(owner=request.user) | Workspace.objects.filter(members=request.user)).distinct()

        try:
            workspace = queryset.get(slug=workspace_slug)
            request.workspace = workspace
        except Workspace.DoesNotExist:
            raise Http404

        return None
