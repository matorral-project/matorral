# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.urls import include, path, re_path
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views import defaults as default_views

from rest_framework.routers import DefaultRouter

from matorral.workspaces import views as workspaces_views
from matorral.sprints import views as sprints_views
from matorral.stories import views as stories_views


router = DefaultRouter()
router.register(r'workspaces', workspaces_views.WorkspaceViewSet)
router.register(r'epics', stories_views.EpicViewSet)
router.register(r'sprints', sprints_views.SprintViewSet)
router.register(r'stories', stories_views.StoryViewSet)
router.register(r'tasks', stories_views.TaskViewSet)

urlpatterns = [
    # Django Admin, use {% url 'admin:index' %}
    re_path(settings.ADMIN_URL, admin.site.urls),

    # health checks
    re_path(r'^health-check/', include('watchman.urls')),
    re_path(r'^health/', include('matorral.health_checks.urls')),

    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), {'next_page': '/'}, name='logout'),

    # User management
    re_path(r'^users/', include('matorral.users.urls')),
    # comments app
    re_path(r'^comments/', include('django_comments_xtd.urls')),

    # API urls
    re_path(r'^api/v1/', include('matorral.authentication.urls')),
    re_path(r'^api/v1/', include(router.urls)),

    # App
    path(r'<workspace>/workspaces/', include('matorral.workspaces.urls', namespace='workspaces')),
    path(r'<workspace>/', include('matorral.stories.urls', namespace='stories')),
    path(r'<workspace>/sprints/', include('matorral.sprints.urls', namespace='sprints')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    import debug_toolbar

    urlpatterns = [  # prepend
        re_path(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

    urlpatterns += [
        path('400/', default_views.bad_request, kwargs={'exception': Exception('Bad Request!')}),
        path('403/', default_views.permission_denied, kwargs={'exception': Exception('Permission Denied')}),
        path('404/', default_views.page_not_found, kwargs={'exception': Exception('Page not Found')}),
        path('500/', default_views.server_error),
    ]
