"""
Audit log utilities for django-auditlog.

Models are registered using the @auditlog.register() decorator directly on each model class.
See:
- apps/projects/models.py (Project)
- apps/sprints/models.py (Sprint)
- apps/issues/models.py (Milestone, Epic, Story, Bug, Chore, Issue)
"""

from django.contrib.contenttypes.models import ContentType

from auditlog.models import LogEntry


def bulk_create_audit_logs(objects, field_name, old_values, new_display, *, actor=None):
    """
    Create LogEntry records for a bulk update using bulk_create.

    Args:
        objects: List of model instances (snapshot before update).
        field_name: The changed field name (e.g., "status", "assignee").
        old_values: Dict mapping pk -> old display value (str or None).
        new_display: Human-readable new value (str or None).
        actor: User who performed the action.
    """
    if not objects:
        return

    # Convert lazy translation proxies to plain strings for JSON serialization
    new_display = str(new_display) if new_display is not None else None

    entries = []
    # Cache content types per model class for non-polymorphic models
    ct_cache = {}

    for obj in objects:
        old_display = old_values.get(obj.pk)
        old_display = str(old_display) if old_display is not None else None
        if old_display == new_display:
            continue

        # For polymorphic models, use the stored polymorphic_ctype_id
        if hasattr(obj, "polymorphic_ctype_id") and obj.polymorphic_ctype_id:
            content_type_id = obj.polymorphic_ctype_id
        else:
            model_class = type(obj)
            if model_class not in ct_cache:
                ct_cache[model_class] = ContentType.objects.get_for_model(model_class)
            content_type_id = ct_cache[model_class].pk

        entries.append(
            LogEntry(
                content_type_id=content_type_id,
                object_id=obj.pk,
                object_pk=str(obj.pk),
                object_repr=str(obj),
                action=LogEntry.Action.UPDATE,
                actor=actor,
                changes={field_name: [old_display, new_display]},
            )
        )

    if entries:
        LogEntry.objects.bulk_create(entries)


def bulk_create_delete_audit_logs(objects, *, actor=None):
    """
    Create LogEntry records with action=DELETE for a batch of model instances.

    Used for cascade deletions where treebeard's queryset-level delete may not
    fire individual post_delete signals.
    """
    if not objects:
        return

    entries = []
    ct_cache = {}

    for obj in objects:
        # For polymorphic models, use the stored polymorphic_ctype_id
        if hasattr(obj, "polymorphic_ctype_id") and obj.polymorphic_ctype_id:
            content_type_id = obj.polymorphic_ctype_id
        else:
            model_class = type(obj)
            if model_class not in ct_cache:
                ct_cache[model_class] = ContentType.objects.get_for_model(model_class)
            content_type_id = ct_cache[model_class].pk

        entries.append(
            LogEntry(
                content_type_id=content_type_id,
                object_id=obj.pk,
                object_pk=str(obj.pk),
                object_repr=str(obj),
                action=LogEntry.Action.DELETE,
                actor=actor,
                changes={},
            )
        )

    if entries:
        LogEntry.objects.bulk_create(entries)
