from rest_framework import serializers

from .models import Sprint


class SprintSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Sprint
        fields = ('title', 'description', 'created_at', 'updated_at', 'starts_at', 'ends_at', 'state')
