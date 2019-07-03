from django.conf.urls import url

from matorral.health_checks.views import liveness, readiness

urlpatterns = [
    url(r'^live/$', liveness),
    url(r'^ready/$', readiness),
]
