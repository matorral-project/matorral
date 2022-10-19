from django.urls import path

from matorral.health_checks.views import liveness, readiness

urlpatterns = [
    path('live/', liveness),
    path('ready/', readiness),
]
