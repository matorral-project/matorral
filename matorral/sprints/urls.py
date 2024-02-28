from django.urls import path

from .views import SprintCreateView, SprintDetailView, SprintList, SprintUpdateView

app_name = "sprints"

urlpatterns = [
    path("add/", SprintCreateView.as_view(), name="sprint-add"),
    path("<int:pk>/", SprintDetailView.as_view(), name="sprint-detail"),
    path("<int:pk>/edit/", SprintUpdateView.as_view(), name="sprint-edit"),
    path("", SprintList.as_view(), name="sprint-list"),
]
