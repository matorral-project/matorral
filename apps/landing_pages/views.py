from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.workspaces.models import Workspace

from health_check.views import MainView


def home(request):
    context = {
        "page_title": "Open Source Project Management tool",
        "page_description": (
            "Project management made simple, built with Django + HTMX + Tailwind. "
            "Open Source. Matorral gives your team a clear, flexible way to plan and deliver software."
        ),
        "og_image": request.build_absolute_uri(static("landing_pages/images/app-screenshot.png")),
        "DEMO_CREDENTIALS_EMAIL": settings.DEMO_CREDENTIALS_EMAIL,
        "DEMO_CREDENTIALS_PASSWORD": settings.DEMO_CREDENTIALS_PASSWORD,
    }
    if request.user.is_authenticated:
        workspace = Workspace.objects.for_user(request.user).first()
        if workspace:
            return HttpResponseRedirect(workspace.get_absolute_url())
        else:
            return render(request, "landing_pages/landing_page.html", context)
    else:
        return render(request, "landing_pages/landing_page.html", context)


@require_GET
@cache_control(max_age=60 * 60 * 24, immutable=True, public=True)  # one day
def favicon(request):
    return HttpResponse(
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="8" fill="#588157"/>'
        '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" '
        'font-family="sans-serif" font-size="9" font-weight="bold" fill="white">matorral</text>'
        "</svg>",
        content_type="image/svg+xml",
    )


def health_check(request, *args, **kwargs):
    tokens = settings.HEALTH_CHECK_TOKENS
    if tokens and request.GET.get("token") not in tokens:
        raise Http404
    return MainView.as_view()(request, *args, **kwargs)


@require_GET
def demo_credentials(request):
    """HTMX endpoint to reveal demo credentials."""
    if not settings.DEMO_CREDENTIALS_EMAIL:
        raise Http404("Demo credentials not configured")
    return render(request, "landing_pages/partials/demo_credentials.html")
