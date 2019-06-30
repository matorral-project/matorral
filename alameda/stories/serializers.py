from alameda.users.serializers import UserSerializer

from rest_framework import serializers

from .models import Epic, EpicState, Story, StoryState, Task


class EpicStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EpicState
        fields = ('slug', 'name')


class StoryStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoryState
        fields = ('slug', 'name')


class EpicSerializer(serializers.HyperlinkedModelSerializer):
    state = EpicStateSerializer()
    owner = UserSerializer()

    class Meta:
        model = Epic
        fields = ('title', 'description', 'priority', 'state', 'owner',
                  'created_at', 'updated_at', 'completed_at')


class TaskItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ('title', 'description', 'created_at', 'updated_at', 'completed_at')


class StorySerializer(serializers.HyperlinkedModelSerializer):
    state = StoryStateSerializer()
    assignee = UserSerializer()
    requester = UserSerializer()

    tasks = TaskItemSerializer(many=True, source='task_set')

    class Meta:
        model = Story
        fields = ('title', 'description', 'epic', 'priority', 'points', 'state',
                  'sprint', 'requester', 'assignee', 'tasks', 'created_at',
                  'updated_at', 'completed_at')


class TaskSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Task
        fields = ('title', 'description', 'story', 'created_at', 'updated_at', 'completed_at')
