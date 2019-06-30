from django.apps import apps
from django.db import models


class BaseModel(models.Model):
    class Meta:
        abstract = True

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title


class ModelWithProgress(models.Model):
    class Meta:
        abstract = True

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    total_points = models.PositiveIntegerField(default=0)
    story_count = models.PositiveIntegerField(default=0)
    points_done = models.PositiveIntegerField(default=0)
    progress = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title

    @staticmethod
    def update_points_and_progress(sender, **kwargs):
        raw = kwargs.get('raw')
        instance = kwargs['instance']

        if raw is None:
            Story = apps.get_model('stories', 'Story')
            StoryState = apps.get_model('stories', 'StoryState')

            for (parent_field, parent) in [('epic', instance.epic), ('sprint', instance.sprint)]:
                if parent is None:
                    continue

                parent_dict = {parent_field: parent}

                total_points = Story.objects.filter(**parent_dict)\
                    .aggregate(models.Sum('points'))['points__sum'] or 0

                params = parent_dict
                params['state__stype'] = StoryState.STATE_DONE
                points_done = Story.objects.filter(**params)\
                    .aggregate(models.Sum('points'))['points__sum'] or 0

                parent.total_points = total_points
                parent.points_done = points_done
                parent.story_count = Story.objects.filter(**parent_dict).count()
                parent.progress = int(points_done / total_points * 100)
                parent.save()
