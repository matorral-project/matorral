from typing import TYPE_CHECKING

from django.apps import apps
from django.db import models
from django.db.models import F, IntegerField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.issues.utils import get_work_item_ctype_ids

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

        BaseIssue = apps.get_model("issues", "BaseIssue")
        done_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "in_progress"]
        todo_statuses = [s for s, cat in BaseIssue.status_categories.items() if cat == "todo"]

        # Query BaseIssue directly filtered by polymorphic_ctype_id — avoids unnecessary
        # JOINs to subclass tables and uses the (project, polymorphic_ctype) index.
        def project_work_items_sum(statuses=None):
            """Sum work items for a project."""
            qs = BaseIssue.objects.non_polymorphic().filter(
                project=OuterRef("pk"),
                polymorphic_ctype_id__in=get_work_item_ctype_ids(),
            )
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

        qs = self.annotate(
            total_done_points=project_work_items_sum(done_statuses),
            total_in_progress_points=project_work_items_sum(in_progress_statuses),
            total_todo_points=project_work_items_sum(todo_statuses),
        )

        return qs.annotate(
            total_estimated_points=F("total_done_points") + F("total_in_progress_points") + F("total_todo_points")
        )
