from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.workspaces.models import Workspace

from health_check.views import MainView


def home(request):
    if request.user.is_authenticated:
        workspace = Workspace.objects.for_user(request.user).first()
        if workspace:
            return HttpResponseRedirect(workspace.get_absolute_url())
        else:
            return render(request, "landing_pages/landing_page.html")
    else:
        return render(request, "landing_pages/landing_page.html")


@require_GET
@cache_control(max_age=60 * 60 * 24, immutable=True, public=True)  # one day
def favicon(request):
    return HttpResponse(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">⚡</text></svg>',
        content_type="image/svg+xml",
    )


def health_check(request, *args, **kwargs):
    tokens = settings.HEALTH_CHECK_TOKENS
    if tokens and request.GET.get("token") not in tokens:
        raise Http404
    return MainView.as_view()(request, *args, **kwargs)
