from django.conf import settings
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify

from simple_history.models import HistoricalRecords

from tagulous.models import TagField

from alameda.models import BaseModel, ModelWithProgress
from alameda.sprints.models import Sprint


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


class Epic(ModelWithProgress):
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

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:epic-view', args=[str(self.id), slugify(self.title)])

    def is_done(self):
        if self.state.stype == StateModel.STATE_DONE:
            return True

        return False

    @staticmethod
    def update_state(sender, **kwargs):
        raw = kwargs['raw']
        instance = kwargs['instance']

        if not raw:
            epic = instance.epic

            if epic is None:
                return

            # set epic as started when it has one or more started stories
            if Story.objects.filter(state__stype=StoryState.STATE_STARTED).count() > 0:
                if epic.state.stype != EpicState.STATE_STARTED:
                    epic.state = EpicState.objects.filter(stype=EpicState.STATE_STARTED)[0]
            elif Story.objects.filter(state__stype=StoryState.STATE_UNSTARTED).count() == epic.story_count:
                if epic.state.stype != EpicState.STATE_UNSTARTED:
                    epic.state = EpicState.objects.filter(stype=EpicState.STATE_UNSTARTED)[0]

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

    def is_done(self):
        if self.state.stype == StateModel.STATE_DONE:
            return True

        return False


@receiver(post_save, sender=Story)
def handle_story_post_save(sender, **kwargs):
    Epic.update_points_and_progress(sender, **kwargs)
    Epic.update_state(sender, **kwargs)


@receiver(post_delete, sender=Story)
def handle_story_post_delete(sender, **kwargs):
    Epic.update_points_and_progress(sender, **kwargs)
    Epic.update_state(sender, **kwargs)


@receiver(post_save, sender=Story)
def handle_story_post_save(sender, **kwargs):
    Sprint.update_points_and_progress(sender, **kwargs)


@receiver(post_delete, sender=Story)
def handle_story_post_delete(sender, **kwargs):
    Sprint.update_points_and_progress(sender, **kwargs)


class Task(BaseModel):
    """
    """
    story = models.ForeignKey(Story, on_delete=models.CASCADE)

    def get_absolute_url(self):
        return reverse('stories:task-view', args=[str(self.id), slugify(self.title)])
