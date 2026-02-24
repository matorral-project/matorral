from typing import TYPE_CHECKING

from django.db import models
from django.db.models import IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

if TYPE_CHECKING:
    from apps.sprints.models import Sprint
    from apps.workspaces.models import Workspace


def _work_item_weight(model, statuses: list[str] | None = None) -> Coalesce:
    """Build a Subquery expression that sums work item weights for a sprint.

    Each item's weight is its estimated_points (or 1 if unset).
    Optionally filters by status values.
    """
    qs = model.objects.filter(sprint_id=OuterRef("pk"))
    if statuses:
        qs = qs.filter(status__in=statuses)
    return Coalesce(
        Subquery(
            qs.values("sprint_id").annotate(total=Sum(Coalesce("estimated_points", Value(1)))).values("total")[:1],
            output_field=IntegerField(),
        ),
        Value(0),
        output_field=IntegerField(),
    )


class SprintQuerySet(models.QuerySet):
    """Custom QuerySet for Sprint model."""

    def for_workspace(self, workspace: Workspace) -> SprintQuerySet:
        """Filter sprints by workspace."""
        return self.filter(workspace=workspace)

    def for_choices(self) -> SprintQuerySet:
        """
        Return only the fields needed for form choice fields.
        Use this when populating ModelChoiceField/ModelMultipleChoiceField querysets.
        """
        return self.only("id", "key", "name")

    def active(self) -> SprintQuerySet:
        """Filter to active sprints."""
        from apps.sprints.models import SprintStatus

        return self.filter(status=SprintStatus.ACTIVE)

    def planning(self) -> SprintQuerySet:
        """Filter to planning sprints."""
        from apps.sprints.models import SprintStatus

        return self.filter(status=SprintStatus.PLANNING)

    def completed(self) -> SprintQuerySet:
        """Filter to completed sprints."""
        from apps.sprints.models import SprintStatus

        return self.filter(status=SprintStatus.COMPLETED)

    def not_archived(self) -> SprintQuerySet:
        """Exclude archived sprints."""
        from apps.sprints.models import SprintStatus

        return self.exclude(status=SprintStatus.ARCHIVED)

    def search(self, query: str) -> SprintQuerySet:
        """Search sprints by name or key (case-insensitive)."""
        if not query:
            return self
        return self.filter(models.Q(name__icontains=query) | models.Q(key__icontains=query))

    def with_key(self, key: str, exclude: Sprint | None = None) -> SprintQuerySet:
        """Filter by key, optionally excluding a specific instance."""
        qs = self.filter(key=key)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def with_key_prefix(self, prefix: str, exclude: Sprint | None = None) -> SprintQuerySet:
        """Filter by key prefix, optionally excluding a specific instance."""
        qs = self.filter(key__startswith=prefix)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def with_progress(self) -> SprintQuerySet:
        """Annotate sprints with progress weights computed at the database level.

        Adds progress_done_weight, progress_in_progress_weight, and
        progress_total_weight annotations by summing work item weights
        (estimated_points or 1) across Story, Bug, and Chore models.
        """
        from apps.issues.models import STATUS_CATEGORIES, Bug, Chore, Story

        done_statuses = [s for s, cat in STATUS_CATEGORIES.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in STATUS_CATEGORIES.items() if cat == "in_progress"]
        models = [Story, Bug, Chore]

        done = sum((_work_item_weight(m, done_statuses) for m in models), Value(0))
        in_progress = sum((_work_item_weight(m, in_progress_statuses) for m in models), Value(0))
        total = sum((_work_item_weight(m) for m in models), Value(0))

        return self.annotate(
            progress_done_weight=done,
            progress_in_progress_weight=in_progress,
            progress_total_weight=total,
        )


class SprintManager(models.Manager):
    """Custom Manager for Sprint model."""

    def get_queryset(self) -> SprintQuerySet:
        return SprintQuerySet(self.model, using=self._db)

    def for_workspace(self, workspace: Workspace) -> SprintQuerySet:
        return self.get_queryset().for_workspace(workspace)
