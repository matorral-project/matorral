from rest_framework import viewsets

from .models import Epic, Story, Task
from .serializers import EpicSerializer, StorySerializer, TaskSerializer


class EpicViewSet(viewsets.ModelViewSet):
    serializer_class = EpicSerializer
    queryset = Epic.objects.all()


class StoryViewSet(viewsets.ModelViewSet):
    serializer_class = StorySerializer
    queryset = Story.objects.all()


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    queryset = Task.objects.all()
