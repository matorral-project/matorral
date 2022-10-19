from django.urls import include, re_path

from rest_framework.authtoken import views

urlpatterns = [
    re_path(r'^api-token-auth/', views.obtain_auth_token),
    re_path(r'^api-auth/', include('rest_framework.urls', namespace='rest_framework')),
]
