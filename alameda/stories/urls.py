from django.urls import path

from .views import EpicCreateView, EpicUpdateView, EpicList, StoryCreateView, StoryList, StoryUpdateView

app_name = 'stories'

urlpatterns = [
    path('epics/add/', EpicCreateView.as_view(), name='epic-add'),
    path('epics/<int:pk>/edit/', EpicUpdateView.as_view(), name='epic-edit'),
    path('epics/', EpicList.as_view(), name='epic-list'),
    path('stories/add/', StoryCreateView.as_view(), name='story-add'),
    path('stories/<int:pk>/edit/', StoryUpdateView.as_view(), name='story-edit'),
    path('', StoryList.as_view(), name='story-list'),
]
