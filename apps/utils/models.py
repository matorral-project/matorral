from django.db import models

from apps.utils.managers import AuditLogManager


class StatusTransitionMixin:
    """
    Model mixin providing a shared _transition_status() helper.

    Concrete start()/complete()/etc. validate preconditions, mutate any
    extra fields, then call _transition_status(). The model's
    @auditlog.register() decorator records the status change on save.
    """

    def _transition_status(self, new_status, extra_update_fields=None):
        """Set status to new_status and save. Pass extra_update_fields for
        any additional fields mutated by the caller before this call."""
        self.status = new_status
        update_fields = ["status", "updated_at"]
        if extra_update_fields:
            update_fields.extend(extra_update_fields)
        self.save(update_fields=update_fields)


class BaseModel(models.Model):
    """
    Base model that includes default created / updated timestamps.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog:
    """
    Proxy class for AuditLog with custom manager methods.

    Provides convenient methods for bulk audit log creation

    Usage:
        AuditLog.objects.bulk_create_for(objects, field_name="status", ...)
        AuditLog.objects.create_for(obj, field_name="status", ...)
    """

    objects = AuditLogManager()
