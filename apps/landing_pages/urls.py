from django.urls import path
from django.views.generic import TemplateView

from apps.landing_pages import views

app_name = "landing_pages"
urlpatterns = [
    path("", views.home, name="home"),
    path("favicon.ico", views.favicon, name="favicon"),
    path(
        "terms/",
        TemplateView.as_view(template_name="landing_pages/terms.html"),
        name="terms",
    ),
    path(
        "privacy/",
        TemplateView.as_view(template_name="landing_pages/privacy.html"),
        name="privacy",
    ),
    path("400/", TemplateView.as_view(template_name="errors/400.html"), name="400"),
    path("403/", TemplateView.as_view(template_name="errors/403.html"), name="403"),
    path("404/", TemplateView.as_view(template_name="errors/404.html"), name="404"),
    path("429/", TemplateView.as_view(template_name="errors/429.html"), name="429"),
    path("500/", TemplateView.as_view(template_name="errors/500.html"), name="500"),
    path("health/", views.health_check, name="health_check"),
]
