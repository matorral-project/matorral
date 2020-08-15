from rest_framework import serializers

from .models import Workspace


class WorkspaceSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Workspace
        fields = ('name', 'description', 'created_at', 'updated_at', 'owner')
