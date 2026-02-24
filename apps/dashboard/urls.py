from django.urls import path

from . import views

workspace_urlpatterns = (
    [
        path("", views.workspace_home, name="home"),
        path("dismiss-onboarding/", views.dismiss_onboarding, name="dismiss_onboarding"),
    ],
    "dashboard",
)
