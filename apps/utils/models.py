from django.db import models

from apps.utils.managers import AuditLogManager


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
