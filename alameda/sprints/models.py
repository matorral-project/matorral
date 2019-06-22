from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from simple_history.models import HistoricalRecords


class Sprint(models.Model):
    """
    """

    STATE_UNSTARTED = 0
    STATE_STARTED = 1
    STATE_DONE = 2

    STATE_TYPES = (
        (STATE_UNSTARTED, 'Unstarted'),
        (STATE_STARTED, 'Started'),
        (STATE_DONE, 'Done'),
    )

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)

    state = models.PositiveIntegerField(db_index=True, choices=STATE_TYPES, default=STATE_UNSTARTED)

    starts_at = models.DateField(db_index=True, null=True, blank=True)
    ends_at = models.DateField(db_index=True, null=True, blank=True)

    created_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('sprints:sprint-view', args=[str(self.id), slugify(self.title)])
