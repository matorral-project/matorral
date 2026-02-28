"""matorral URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/stable/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.i18n import JavaScriptCatalog

from apps.issues.urls import milestones_urlpatterns as milestones_project_urls
from apps.issues.urls import project_urlpatterns as issues_project_urls
from apps.issues.urls import workspace_urlpatterns as issues_workspace_urls
from apps.projects.urls import project_urlpatterns as projects_project_urls
from apps.sprints.urls import workspace_urlpatterns as sprints_urls
from apps.users.views import CustomPasswordChangeView
from apps.workspaces.urls import standalone_urlpatterns as workspaces_standalone_urls

handler400 = "matorral.error_views.bad_request"
handler403 = "matorral.error_views.permission_denied"
handler404 = "matorral.error_views.page_not_found"
handler429 = "matorral.error_views.too_many_requests"
handler500 = "matorral.error_views.server_error"

urlpatterns = [
    path("__reload__/", include("django_browser_reload.urls")),
    # redirect Django admin login to main login page
    path("admin/login/", RedirectView.as_view(pattern_name="account_login")),
    path("admin/", admin.site.urls),
    # Standalone workspace URLs (list, create, invitations) must come first so
    # fixed paths like "create/" are matched before the catch-all <workspace_slug>/ pattern.
    path("w/", include(workspaces_standalone_urls)),
    # Workspace-scoped URLs
    path("w/<slug:workspace_slug>/p/", include(projects_project_urls)),
    path("w/<slug:workspace_slug>/p/<str:project_key>/issues/", include(issues_project_urls)),
    path(
        "w/<slug:workspace_slug>/p/<str:project_key>/milestones/",
        include((milestones_project_urls, "milestones")),
    ),
    path("w/<slug:workspace_slug>/issues/", include(issues_workspace_urls)),
    path("w/<slug:workspace_slug>/sprints/", include((sprints_urls, "sprints"))),
    path("i18n/", include("django.conf.urls.i18n")),
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    # Custom password change view with HTMX support (before allauth)
    path(
        "accounts/password/change/",
        CustomPasswordChangeView.as_view(),
        name="account_change_password",
    ),
    path("accounts/", include("allauth.urls")),
    path("users/", include("apps.users.urls")),
    path("", include("apps.landing_pages.urls")),
    path("celery-progress/", include("celery_progress.urls")),
    # hijack urls for impersonation
    path("hijack/", include("hijack.urls", namespace="hijack")),
    # django-comments-xtd urls
    path("comments/", include("django_comments_xtd.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.ENABLE_DEBUG_TOOLBAR:
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
