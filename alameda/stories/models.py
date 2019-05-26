from django.conf import settings
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify

from simple_history.models import HistoricalRecords

from tagulous.models import TagField


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


class StateModel(models.Model):
    class Meta:
        abstract = True
        ordering = ['stype', 'name']

    STATE_UNSTARTED = 0
    STATE_STARTED = 1
    STATE_DONE = 2

    STATE_TYPES = (
        (STATE_UNSTARTED, 'Unstarted'),
        (STATE_STARTED, 'Started'),
        (STATE_DONE, 'Done'),
    )

    slug = models.SlugField(max_length=2, primary_key=True)
    name = models.CharField(max_length=100, db_index=True)
    stype = models.PositiveIntegerField(db_index=True, choices=STATE_TYPES, default=STATE_UNSTARTED)

    def __str__(self):
        return self.name


class EpicState(StateModel):
    pass


class StoryState(StateModel):
    pass


class Epic(BaseModel):
    """
    """

    class Meta:
        get_latest_by = 'created_at'
        ordering = ['priority', '-title']
        indexes = [
            models.Index(fields=['title', 'priority']),
            models.Index(fields=['title']),
        ]
        verbose_name = 'epic'
        verbose_name_plural = 'epics'

    priority = models.PositiveIntegerField(default=0)
    state = models.ForeignKey(EpicState, on_delete=models.SET_NULL, null=True, blank=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    total_points = models.PositiveIntegerField(default=0)
    story_count = models.PositiveIntegerField(default=0)
    points_done = models.PositiveIntegerField(default=0)
    progress = models.PositiveIntegerField(default=0)

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:epic-view', args=[str(self.id), slugify(self.title)])

    @staticmethod
    def update_points_and_progress(sender, **kwargs):
        raw = kwargs['raw']
        instance = kwargs['instance']

        if not raw:
            epic = instance.epic

            total_points = Story.objects.filter(epic=epic)\
                .aggregate(models.Sum('points'))['points__sum'] or 0
            points_done = Story.objects.filter(state__stype=EpicState.STATE_DONE, epic=epic)\
                .aggregate(models.Sum('points'))['points__sum'] or 0

            epic.total_points = total_points
            epic.points_done = points_done
            epic.story_count = Story.objects.filter(epic=epic).count()
            epic.progress = int(points_done / total_points * 100)
            epic.save()


class Story(BaseModel):
    """
    """
    class Meta:
        get_latest_by = 'created_at'
        ordering = ['priority', '-title']
        indexes = [
            models.Index(fields=['title', 'priority']),
            models.Index(fields=['title']),
        ]
        verbose_name = 'story'
        verbose_name_plural = 'stories'

    epic = models.ForeignKey(Epic, null=True, blank=True, on_delete=models.SET_NULL)
    priority = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=0)
    state = models.ForeignKey(StoryState, on_delete=models.SET_NULL, null=True, blank=True)

    sprint = models.ForeignKey('sprints.Sprint', null=True, blank=True, on_delete=models.SET_NULL)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_tasks')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks')

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:story-view', args=[str(self.id), slugify(self.title)])


@receiver(post_save, sender=Story)
def handle_story_post_save(sender, **kwargs):
    Epic.update_points_and_progress(sender, **kwargs)


@receiver(post_delete, sender=Story)
def handle_story_post_delete(sender, **kwargs):
    Epic.update_points_and_progress(sender, **kwargs)


class Task(BaseModel):
    """
    """
    story = models.ForeignKey(Story, on_delete=models.CASCADE)

    def get_absolute_url(self):
        return reverse('stories:task-view', args=[str(self.id), slugify(self.title)])
