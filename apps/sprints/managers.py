from datetime import timedelta
from typing import TYPE_CHECKING

from django.apps import apps
from django.db import models
from django.db.models import Case, IntegerField, OuterRef, Subquery, Sum, Value, When
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


def _work_item_points(model, statuses: list[str] | None = None) -> Coalesce:
    """Build a Subquery expression that sums estimated_points for a sprint.

    Unlike _work_item_weight, this uses raw estimated_points without
    defaulting unset values to 1.
    Optionally filters by status values.
    """
    qs = model.objects.filter(sprint_id=OuterRef("pk"))
    if statuses:
        qs = qs.filter(status__in=statuses)
    return Coalesce(
        Subquery(
            qs.values("sprint_id").annotate(total=Sum("estimated_points")).values("total")[:1],
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
        return self.filter(status=self.model.status_model.ACTIVE)

    def planning(self) -> SprintQuerySet:
        """Filter to planning sprints."""
        return self.filter(status=self.model.status_model.PLANNING)

    def completed(self) -> SprintQuerySet:
        """Filter to completed sprints."""
        return self.filter(status=self.model.status_model.COMPLETED)

    def not_archived(self) -> SprintQuerySet:
        """Exclude archived sprints."""
        return self.exclude(status=self.model.status_model.ARCHIVED)

    def available(self) -> SprintQuerySet:
        """Sprints that can receive work items (planning or active), active first then newest."""
        return (
            self.filter(status__in=[self.model.status_model.PLANNING, self.model.status_model.ACTIVE])
            .annotate(
                status_order=Case(
                    When(status=self.model.status_model.ACTIVE, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("status_order", "-start_date")
        )

    def latest_active_or_completed(self) -> Sprint | None:
        """Return the most recent active or completed sprint."""
        return (
            self.filter(status__in=[self.model.status_model.ACTIVE, self.model.status_model.COMPLETED])
            .order_by("-end_date")
            .first()
        )

    def has_next_planning(self, after_date) -> bool:
        """Check if a planning sprint exists after the given date."""
        return self.filter(start_date__gt=after_date, status=self.model.status_model.PLANNING).exists()

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

    def with_committed_points(self) -> SprintQuerySet:
        """Annotate sprints with committed points (sum of estimated_points across all work items)."""
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")

        total = sum((_work_item_points(m) for m in [Story, Bug, Chore]), Value(0))
        return self.annotate(computed_committed_points=total)

    def with_completed_points(self) -> SprintQuerySet:
        """Annotate sprints with completed points (sum of estimated_points for done work items)."""
        BaseIssue = apps.get_model("issues", "BaseIssue")
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")

        done_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "done"]
        total = sum((_work_item_points(m, done_statuses) for m in [Story, Bug, Chore]), Value(0))
        return self.annotate(computed_completed_points=total)

    def with_velocity(self) -> SprintQuerySet:
        """Annotate sprints with both committed and completed points."""
        return self.with_committed_points().with_completed_points()

    def with_progress(self) -> SprintQuerySet:
        """Annotate sprints with progress weights computed at the database level.

        Adds total_estimated_points, total_done_points, total_in_progress_points,
        and total_todo_points annotations by summing work item weights
        (estimated_points or 1) across Story, Bug, and Chore models.
        """

        BaseIssue = apps.get_model("issues", "BaseIssue")
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")

        done_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "in_progress"]

        models = [Story, Bug, Chore]

        done = sum((_work_item_weight(m, done_statuses) for m in models), Value(0))
        in_progress = sum((_work_item_weight(m, in_progress_statuses) for m in models), Value(0))
        total = sum((_work_item_weight(m) for m in models), Value(0))

        return self.annotate(
            total_done_points=done,
            total_in_progress_points=in_progress,
            total_todo_points=total - done - in_progress,
            total_estimated_points=total,
        )


class SprintManager(models.Manager):
    """Custom Manager for Sprint model."""

    def get_queryset(self) -> SprintQuerySet:
        return SprintQuerySet(self.model, using=self._db)

    def for_workspace(self, workspace: Workspace) -> SprintQuerySet:
        return self.get_queryset().for_workspace(workspace)

    def create_next_from(self, previous: Sprint) -> Sprint:
        """Create the next sprint based on a previous sprint's settings."""
        duration = previous.end_date - previous.start_date
        sprint = self.create(
            workspace=previous.workspace,
            name="",
            start_date=previous.end_date + timedelta(days=1),
            end_date=previous.end_date + timedelta(days=1) + duration,
            status=self.model.status_model.PLANNING,
            capacity=previous.capacity,
        )
        sprint_number = sprint.key.split("-")[-1]
        sprint.name = f"Sprint #{sprint_number}"
        sprint.save(update_fields=["name"])
        return sprint

    def get_creation_defaults(self, workspace: Workspace, workspace_members) -> dict:
        """Return initial dict for sprint create form based on latest sprint data."""
        initial = {}

        if workspace_members is not None and len(workspace_members) == 1:
            initial["owner"] = workspace_members[0].pk

        try:
            latest_sprint = (
                self.for_workspace(workspace).values("owner_id", "capacity", "status", "end_date").latest("created_at")
            )

            if "owner" not in initial and latest_sprint["owner_id"]:
                initial["owner"] = latest_sprint["owner_id"]

            if latest_sprint["capacity"]:
                initial["capacity"] = latest_sprint["capacity"]

            if latest_sprint["status"] == self.model.status_model.COMPLETED:
                initial["start_date"] = latest_sprint["end_date"]
                initial["end_date"] = latest_sprint["end_date"] + timedelta(days=7)
            else:
                try:
                    latest_completed = self.for_workspace(workspace).completed().values("end_date").latest("end_date")
                    initial["start_date"] = latest_completed["end_date"]
                    initial["end_date"] = latest_completed["end_date"] + timedelta(days=7)
                except self.model.DoesNotExist:
                    pass
        except self.model.DoesNotExist:
            pass

        return initial
