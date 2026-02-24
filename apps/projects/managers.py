from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.projects.models import Project
    from apps.workspaces.models import Workspace


class ProjectQuerySet(models.QuerySet):
    """Custom QuerySet for Project model."""

    def for_workspace(self, workspace: Workspace) -> ProjectQuerySet:
        """Filter projects by workspace."""
        return self.filter(workspace=workspace)

    def for_choices(self) -> ProjectQuerySet:
        """
        Return only the fields needed for form choice fields.
        Use this when populating ModelChoiceField/ModelMultipleChoiceField querysets.
        """
        return self.only("id", "key", "name")

    def search(self, query: str) -> ProjectQuerySet:
        """Search projects by name or key (case-insensitive)."""
        if not query:
            return self
        return self.filter(models.Q(name__icontains=query) | models.Q(key__icontains=query))

    def with_key(self, key: str, exclude: Project | None = None) -> ProjectQuerySet:
        """Filter by key, optionally excluding a specific project instance."""
        qs = self.filter(key=key)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def set_draft(self) -> int:
        """Set status to draft for all projects in queryset. Returns count of updated rows."""
        from apps.projects.models import ProjectStatus

        return self.update(status=ProjectStatus.DRAFT)

    def set_active(self) -> int:
        """Set status to active for all projects in queryset. Returns count of updated rows."""
        from apps.projects.models import ProjectStatus

        return self.update(status=ProjectStatus.ACTIVE)

    def set_completed(self) -> int:
        """Set status to completed for all projects in queryset. Returns count of updated rows."""
        from apps.projects.models import ProjectStatus

        return self.update(status=ProjectStatus.COMPLETED)

    def set_archived(self) -> int:
        """Set status to archived for all projects in queryset. Returns count of updated rows."""
        from apps.projects.models import ProjectStatus

        return self.update(status=ProjectStatus.ARCHIVED)
