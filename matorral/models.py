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

    def update_points_and_progress(self, save=True):
        Story = apps.get_model("stories", "Story")
        StoryState = apps.get_model("stories", "StoryState")

        parent_dict = {self._meta.model_name: self.id}

        # calculate total points
        total_points = Story.objects.filter(**parent_dict).aggregate(models.Sum("points"))["points__sum"] or 0

        if total_points == 0:
            # if no story has points, then count the stories
            total_points = Story.objects.filter(**parent_dict).count()

        # calculate points done
        params = parent_dict.copy()
        params["state__stype"] = StoryState.STATE_DONE
        points_done = Story.objects.filter(**params).aggregate(models.Sum("points"))["points__sum"] or 0

        if points_done == 0:
            # if no story has points, then count the stories
            points_done = Story.objects.filter(**params).count()

        self.total_points = total_points
        self.points_done = points_done
        self.story_count = Story.objects.filter(**parent_dict).count()

        self.progress = int(float(points_done) / (total_points or 1) * 100)

        if save:
            self.save()
