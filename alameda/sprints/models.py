from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from simple_history.models import HistoricalRecords

from alameda.models import BaseModel


class Sprint(BaseModel):
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

    state = models.PositiveIntegerField(db_index=True, choices=STATE_TYPES, default=STATE_UNSTARTED)

    starts_at = models.DateField(db_index=True, null=True, blank=True)
    ends_at = models.DateField(db_index=True, null=True, blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('sprints:sprint-view', args=[str(self.id), slugify(self.title)])

    def is_done(self):
        return self.state == self.STATE_DONE

    def is_started(self):
        return self.state == self.STATE_STARTED
