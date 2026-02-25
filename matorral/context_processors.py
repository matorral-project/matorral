from django.conf import settings
from django.contrib.sites.models import Site


def get_root(is_secure: bool = settings.USE_HTTPS_IN_ABSOLUTE_URLS) -> str:
    protocol = settings.USE_HTTPS_IN_ABSOLUTE_URLS and "https" or "http"
    return f"{protocol}://{Site.objects.get_current().domain}"


_ENV_BADGE_LABELS = {
    "local": "local",
    "production": "beta",
}


def base_context(request):
    environment = getattr(settings, "ENVIRONMENT", "local")
    return {
        "site": Site.objects.get_current(request),
        "server_url": get_root(),
        "page_url": get_root() + request.path,
        "site_description": getattr(settings, "SITE_DESCRIPTION", ""),
        "site_keywords": getattr(settings, "SITE_KEYWORDS", ""),
        "is_debug": settings.DEBUG,
        "env_badge": _ENV_BADGE_LABELS.get(environment, "demo"),
    }


def google_analytics_id(request):
    """Adds google analytics id to all requests."""
    if settings.GOOGLE_ANALYTICS_ID:
        return {"GOOGLE_ANALYTICS_ID": settings.GOOGLE_ANALYTICS_ID}
    return {}
