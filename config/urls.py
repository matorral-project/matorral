from django.conf import settings
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views import defaults as default_views

from matorral.workspaces.views import workspace_index


urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    re_path(settings.ADMIN_URL, admin.site.urls),
    # health checks
    re_path(r"^health-check/", include("watchman.urls")),
    re_path(r"^health/", include("matorral.health_checks.urls")),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), {"next_page": "/"}, name="logout"),
    # User management
    re_path(r"^users/", include("matorral.users.urls")),
    # App
    path(r"<workspace>/", include("matorral.stories.urls", namespace="stories")),
    path(r"<workspace>/sprints/", include("matorral.sprints.urls", namespace="sprints")),
    path(r"", workspace_index, name="workspace:index"),  # disabled for now, until we finish all the features
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    import debug_toolbar

    urlpatterns = [  # prepend
        re_path(r"^__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

    urlpatterns += [
        path("400/", default_views.bad_request, kwargs={"exception": Exception("Bad Request!")}),
        path("403/", default_views.permission_denied, kwargs={"exception": Exception("Permission Denied")}),
        path("404/", default_views.page_not_found, kwargs={"exception": Exception("Page not Found")}),
        path("500/", default_views.server_error),
    ]
