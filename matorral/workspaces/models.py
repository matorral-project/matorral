import copy

from django.conf import settings
from django.db import models


class Workspace(models.Model):
    """ """

    slug = models.SlugField(max_length=100, db_index=True, default="default")

    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, null=True)

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="members_set", blank=True)

    created_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        unique_together = ("slug", "owner")
        get_latest_by = "created_at"
        ordering = ["owner", "name"]
        verbose_name = "workspace"
        verbose_name_plural = "workspaces"

    def __str__(self):
        return self.name

    def duplicate(self):
        cloned = copy.copy(self)
        cloned.pk = None
        cloned.name = "Copy of " + self.name
        cloned.slug = self.slug + "-copy"
        cloned.save()
