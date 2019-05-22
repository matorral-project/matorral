from django.db import models
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

    slug = models.SlugField(max_length=2, primary_key=True)
    name = models.CharField(max_length=100, db_index=True)

    def __str__(self):
        return self.name


class EpicState(StateModel):
    pass


class StoryState(StateModel):
    pass


class Sprint(BaseModel):
    """
    """

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:sprint-view', args=[str(self.id), slugify(self.title)])


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

    owner = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:epic-view', args=[str(self.id), slugify(self.title)])


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

    sprint = models.ForeignKey(Sprint, null=True, blank=True, on_delete=models.SET_NULL)

    owner = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_tasks')
    assignee = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks')

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:story-view', args=[str(self.id), slugify(self.title)])


class Task(BaseModel):
    """
    """
    story = models.ForeignKey(Story, on_delete=models.CASCADE)

    def get_absolute_url(self):
        return reverse('stories:task-view', args=[str(self.id), slugify(self.title)])
