import copy

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.urls import reverse

from simple_history.models import HistoricalRecords

from tagulous.models import TagField

from matorral.models import BaseModel, ModelWithProgress


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
    
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE)

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:epic-detail', args=[self.workspace.slug, str(self.id)])

    def is_done(self):
        if self.state.stype == StateModel.STATE_DONE:
            return True

        return False

    def duplicate(self):
        cloned = copy.copy(self)
        cloned.pk = None
        cloned.title = 'Copy of ' + self.title
        cloned.save()

        for tag in self.tags.values_list('name', flat=True):
            cloned.tags.add(tag)

    def update_state(self):
        # set epic as started when it has one or more started stories
        if Story.objects.filter(state__stype=StoryState.STATE_STARTED, epic=self).count() > 0:
            if self.state.stype != EpicState.STATE_STARTED:
                self.state = EpicState.objects.filter(stype=EpicState.STATE_STARTED)[0]

        elif Story.objects.filter(state__stype=StoryState.STATE_UNSTARTED, epic=self).count() == self.story_count:
            if self.state.stype != EpicState.STATE_UNSTARTED:
                self.state = EpicState.objects.filter(stype=EpicState.STATE_UNSTARTED)[0]

        self.save()


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

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='requested_tasks')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks')

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE)

    tags = TagField(blank=True)

    history = HistoricalRecords()

    def get_absolute_url(self):
        return reverse('stories:story-detail', args=[self.workspace.slug, str(self.id)])

    def is_done(self):
        if self.state.stype == StateModel.STATE_DONE:
            return True

        return False

    def duplicate(self):
        cloned = copy.copy(self)
        cloned.pk = None
        cloned.title = 'Copy of ' + self.title
        cloned.save()

        for task in self.task_set.all():
            task.duplicate(story=cloned)

        for tag in self.tags.values_list('name', flat=True):
            cloned.tags.add(tag)


@receiver(pre_save, sender=Story)
def handle_story_pre_save(sender, **kwargs):
    if not kwargs.get('raw', False):
        instance = kwargs['instance']

        if instance.id is None:
            previous_epic = None
        else:
            try:
                previous_epic = Epic.objects.get(story__id=instance.id)
            except Epic.DoesNotExist:
                previous_epic = None

        # the epic has changed: update here the previous one,
        # the new one will be updated in post_save handler :)
        if (previous_epic != instance.epic) and previous_epic is not None:
            from .tasks import handle_epic_change
            # 10 seconds till the epic changes to the new one so this will have
            # one story less
            handle_epic_change.apply_async((previous_epic.id, ), countdown=10)

        if instance.id is None:
            previous_sprint = None
        else:
            from matorral.sprints.models import Sprint
            try:
                previous_sprint = Sprint.objects.get(story__id=instance.id)
            except Sprint.DoesNotExist:
                previous_sprint = None

        # the sprint has changed: update here the previous one,
        # the new one will be updated in post_save handler :)
        if (previous_sprint != instance.sprint) and previous_sprint is not None:
            from matorral.sprints.tasks import handle_sprint_change
            # 10 seconds till the sprint changes to the new one so this will have
            # one story less
            handle_sprint_change.apply_async((previous_sprint.id, ), countdown=10)


@receiver(post_save, sender=Story)
def handle_story_post_save(sender, **kwargs):
    from .tasks import handle_story_change
    if not kwargs.get('raw', False):
        instance = kwargs['instance']
        handle_story_change.delay(instance.id)


@receiver(post_delete, sender=Story)
def handle_story_post_delete(sender, **kwargs):
    from .tasks import handle_story_change
    if not kwargs.get('raw', False):
        instance = kwargs['instance']
        handle_story_change.delay(instance.id)


class Task(BaseModel):
    """
    """
    story = models.ForeignKey(Story, on_delete=models.CASCADE)

    def get_absolute_url(self):
        return reverse('stories:task-view', args=[str(self.id)])

    def duplicate(self, parent=None):
        cloned = copy.copy(self)
        cloned.pk = None
        cloned.title = self.title

        if parent is not None:
            cloned.story = parent

        cloned.save()
