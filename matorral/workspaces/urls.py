from django.urls import path

from .views import WorkspaceCreateView, WorkspaceDetailView, WorkspaceList, WorkspaceUpdateView

app_name = 'workspaces'

urlpatterns = [
    path('add/', WorkspaceCreateView.as_view(), name='workspace-add'),
    path('<int:pk>/', WorkspaceDetailView.as_view(), name='workspace-detail'),
    path('<int:pk>/edit/', WorkspaceUpdateView.as_view(), name='workspace-edit'),
    path('', WorkspaceList.as_view(), name='workspace-list'),
]
