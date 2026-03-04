from typing import TYPE_CHECKING

from django.apps import apps
from django.db import models
from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

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
        return self.update(status=self.model.status_model.DRAFT)

    def set_active(self) -> int:
        """Set status to active for all projects in queryset. Returns count of updated rows."""
        return self.update(status=self.model.status_model.ACTIVE)

    def set_completed(self) -> int:
        """Set status to completed for all projects in queryset. Returns count of updated rows."""
        return self.update(status=self.model.status_model.COMPLETED)

    def set_archived(self) -> int:
        """Set status to archived for all projects in queryset. Returns count of updated rows."""
        return self.update(status=self.model.status_model.ARCHIVED)

    def with_progress(self) -> ProjectQuerySet:
        """Annotate projects with progress from work items.

        Adds total_estimated_points, total_done_points, total_in_progress_points,
        and total_todo_points annotations by summing work item weights from all
        issues in the project.

        Work items are Story, Bug, and Chore models (using instance_of()).
        """

        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        Story = apps.get_model("issues", "Story")

        # Get status categories for filtering
        BaseIssue = apps.get_model("issues", "BaseIssue")
        done_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "in_progress"]
        todo_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "todo"]

        # For each project, sum work items directly filtered by project
        def project_work_items_sum(model, statuses=None):
            """Sum work items for a project."""
            qs = model.objects.filter(project=OuterRef("pk"))
            if statuses:
                qs = qs.filter(status__in=statuses)

            return Coalesce(
                Subquery(
                    qs.values("project")
                    .annotate(total=Sum(Coalesce("estimated_points", Value(1))))
                    .values("total")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            )

        # Annotate with progress from project work items
        qs = self.annotate(
            total_done_points=(
                project_work_items_sum(Story, done_statuses)
                + project_work_items_sum(Bug, done_statuses)
                + project_work_items_sum(Chore, done_statuses)
            ),
            total_in_progress_points=(
                project_work_items_sum(Story, in_progress_statuses)
                + project_work_items_sum(Bug, in_progress_statuses)
                + project_work_items_sum(Chore, in_progress_statuses)
            ),
            total_todo_points=(
                project_work_items_sum(Story, todo_statuses)
                + project_work_items_sum(Bug, todo_statuses)
                + project_work_items_sum(Chore, todo_statuses)
            ),
        )

        # total_estimated_points = done + in_progress + todo
        return qs.annotate(
            total_estimated_points=F("total_done_points") + F("total_in_progress_points") + F("total_todo_points")
        )
