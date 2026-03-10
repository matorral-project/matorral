from django.contrib.contenttypes.models import ContentType

from auditlog.models import LogEntry as AuditLogEntry
from auditlog.models import LogEntryManager


class AuditLogManager(LogEntryManager):
    """Custom manager for AuditLog with bulk operations."""

    def create_for(
        self,
        obj,
        *,
        actor=None,
        field_name=None,
        old_value=None,
        new_value=None,
    ):
        """
        Create a single audit log entry for an object.

        Auto-detects action type:
        - UPDATE: when field_name is provided
        - DELETE: when field_name is None

        Args:
            obj: The model instance to log.
            actor: User who performed the action.
            field_name: For updates, the field that changed.
            old_value: For updates, the old value (for display).
            new_value: For updates, the new value (for display).

        Returns:
            The created LogEntry instance, or None if no changes (for updates).
        """
        if field_name is not None:
            # UPDATE action
            old_display = str(old_value) if old_value is not None else None
            new_display = str(new_value) if new_value is not None else None

            # Skip if values are the same
            if old_display == new_display:
                return None

            action = AuditLogEntry.Action.UPDATE
            changes = {field_name: [old_display, new_display]}
        else:
            # DELETE action
            action = AuditLogEntry.Action.DELETE
            changes = {}

        entry = AuditLogEntry(
            content_type_id=self._get_content_type_id(obj),
            object_id=obj.pk,
            object_pk=str(obj.pk),
            object_repr=str(obj),
            action=action,
            actor=actor,
            changes=changes,
        )
        entry.save(force_insert=True)
        return entry

    def bulk_create_for(
        self,
        objects,
        *,
        actor=None,
        field_name=None,
        old_values=None,
        new_display=None,
    ):
        """
        Bulk create audit log entries for multiple objects.

        Auto-detects action type:
        - UPDATE: when field_name is provided
        - DELETE: when field_name is None

        Args:
            objects: Iterable of model instances to log.
            actor: User who performed the action.
            field_name: For updates, the field that changed.
            old_values: For updates, dict mapping pk -> old display value.
            new_display: For updates, the new display value.

        Returns:
            Number of entries created.
        """
        if not objects:
            return 0

        entries = []
        ct_cache = {}

        for obj in objects:
            entry = self._build_entry(obj, field_name, old_values, new_display, ct_cache, actor)
            if entry:
                entries.append(entry)

        if entries:
            AuditLogEntry.objects.bulk_create(entries)
            return len(entries)
        return 0

    def _build_entry(
        self,
        obj,
        field_name,
        old_values,
        new_display,
        ct_cache,
        actor,
    ):
        """Build a LogEntry instance with auto-detection."""
        content_type_id = self._get_content_type_id(obj, ct_cache)

        if field_name is not None:
            # UPDATE action
            old_display = None
            if old_values:
                old_val = old_values.get(obj.pk)
                old_display = str(old_val) if old_val is not None else None
            new_display_str = str(new_display) if new_display is not None else None

            if old_display == new_display_str:
                return None

            action = AuditLogEntry.Action.UPDATE
            changes = {field_name: [old_display, new_display_str]}
        else:
            # DELETE action
            action = AuditLogEntry.Action.DELETE
            changes = {}

        return AuditLogEntry(
            content_type_id=content_type_id,
            object_id=obj.pk,
            object_pk=str(obj.pk),
            object_repr=str(obj),
            action=action,
            actor=actor,
            changes=changes,
        )

    def _get_content_type_id(self, obj, ct_cache=None):
        """Get content type ID with optional caching."""
        if hasattr(obj, "polymorphic_ctype_id") and obj.polymorphic_ctype_id:
            return obj.polymorphic_ctype_id

        if ct_cache is not None:
            model_class = type(obj)
            if model_class not in ct_cache:
                ct_cache[model_class] = self._get_content_type_for_model(model_class)
            return ct_cache[model_class]

        return self._get_content_type_for_model(type(obj))

    def _get_content_type_for_model(self, model_class):
        """Get content type ID for a model class."""
        return ContentType.objects.get_for_model(model_class).pk
