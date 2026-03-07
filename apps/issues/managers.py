from typing import TYPE_CHECKING

from django.apps import apps
from django.db import models
from django.db.models import Case, F, Func, IntegerField, OuterRef, Q, QuerySet, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.issues.helpers import _work_item_weight

from polymorphic.managers import PolymorphicManager
from polymorphic.query import PolymorphicQuerySet
from treebeard.mp_tree import MP_NodeQuerySet

if TYPE_CHECKING:
    from apps.issues.models import BaseIssue, IssueStatus, Milestone
    from apps.projects.models import Project
    from apps.sprints.models import Sprint
    from apps.users.models import User
    from apps.workspaces.models import Workspace


class KeyNumber(Func):
    """
    Database function to extract the numeric suffix from an issue key.
    Keys have format '{PROJECT_KEY}-{NUMBER}' (e.g., 'SRM-123').
    Returns the numeric part as an integer for proper sorting.
    """

    function = "CAST"
    template = "CAST(SUBSTRING(%(expressions)s FROM '-([0-9]+)$') AS INTEGER)"
    output_field = IntegerField()


class IssueQuerySet(MP_NodeQuerySet, PolymorphicQuerySet):
    """Custom QuerySet for Issue models.

    Inherits from both MP_NodeQuerySet and PolymorphicQuerySet to ensure:
    - Tree-aware deletion (MP_NodeQuerySet.delete() cascades to descendants)
    - Polymorphic model support (returns correct subclass instances)
    """

    def for_project(self, project: Project) -> IssueQuerySet:
        """Filter issues by project."""
        return self.filter(project=project)

    def for_choices(self) -> IssueQuerySet:
        """
        Return only the fields needed for form choice fields.
        Use this when populating ModelChoiceField/ModelMultipleChoiceField querysets.
        Note: polymorphic_ctype_id is required for polymorphic model functionality.
        """
        return self.only("id", "key", "title", "polymorphic_ctype_id")

    def for_workspace(self, workspace: Workspace) -> IssueQuerySet:
        """Filter issues by workspace (through project)."""
        return self.filter(project__workspace=workspace)

    def for_sprint(self, sprint: Sprint) -> IssueQuerySet:
        """Filter to work items assigned to a sprint."""

        # Check if we're already querying a specific work item type
        # (not BaseIssue polymorphic queryset)
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        model = getattr(self, "model", None)
        if model in (Story, Bug, Chore):
            # Already a specific work item type, filter directly on sprint field
            return self.filter(sprint=sprint)

        return self.filter(Q(story__sprint=sprint) | Q(bug__sprint=sprint) | Q(chore__sprint=sprint))

    def work_items(self) -> IssueQuerySet:
        """Filter to work items only (Story, Bug, Chore)."""
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        return self.instance_of(Story, Bug, Chore)

    def backlog(self) -> IssueQuerySet:
        """Filter to work items NOT assigned to any sprint.

        Returns only work items (Story, Bug, Chore) that have no sprint.
        Epics don't have sprints and are excluded from this filter.
        """
        # Get work items and exclude those that have a sprint assigned.
        # Since sprint is on each subclass, we need to exclude based on each relation.

        return (
            self.work_items()
            .exclude(story__sprint__isnull=False)
            .exclude(bug__sprint__isnull=False)
            .exclude(chore__sprint__isnull=False)
        )

    def of_type(self, *types: type) -> IssueQuerySet:
        """Filter to specific issue types."""
        return self.instance_of(*types)

    def roots(self) -> IssueQuerySet:
        """Filter to root-level issues (no parent)."""
        return self.filter(depth=1)

    def with_status(self, status: IssueStatus) -> IssueQuerySet:
        """Filter by status."""
        return self.filter(status=status)

    def active(self) -> IssueQuerySet:
        """Filter to active issues (not archived, done, or won't do)."""
        return self.exclude(
            status__in=[self.model.status_model.ARCHIVED, self.model.status_model.DONE, self.model.status_model.WONT_DO]
        )

    def done(self) -> IssueQuerySet:
        """Filter to done issues (done, archived, or won't do)."""
        return self.filter(
            status__in=[self.model.status_model.DONE, self.model.status_model.ARCHIVED, self.model.status_model.WONT_DO]
        )

    def search(self, query: str) -> IssueQuerySet:
        """Search issues by title or key (case-insensitive)."""
        if not query:
            return self
        return self.filter(models.Q(title__icontains=query) | models.Q(key__icontains=query))

    def with_assignee(self, user: User) -> IssueQuerySet:
        """Filter to issues assigned to a user."""
        return self.filter(assignee=user)

    def unassigned(self) -> IssueQuerySet:
        """Filter to unassigned issues."""
        return self.filter(assignee__isnull=True)

    def overdue(self) -> IssueQuerySet:
        """Filter to overdue issues (due_date in the past and not done/archived/won't do)."""
        return self.filter(due_date__lt=timezone.now().date()).exclude(
            status__in=[self.model.status_model.DONE, self.model.status_model.ARCHIVED, self.model.status_model.WONT_DO]
        )

    def with_key(self, key: str, exclude: BaseIssue | None = None) -> IssueQuerySet:
        """Filter by key, optionally excluding a specific instance."""
        qs = self.filter(key=key)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def for_milestone(self, milestone: Milestone) -> IssueQuerySet:
        """Filter to epics linked to milestone plus all their descendants.

        Uses the reverse relation (milestone.epics) to avoid circular imports.
        Returns issues whose path matches any epic's path as a prefix.
        """
        epic_paths = list(milestone.epics.values_list("path", flat=True))
        if not epic_paths:
            return self.none()

        # Match epics and all their descendants using path prefix
        path_regex = r"^(" + "|".join(epic_paths) + r")"
        return self.filter(path__regex=path_regex)

    def ordered_by_key(self) -> IssueQuerySet:
        """
        Order issues by their key numerically.
        Keys have format '{PROJECT_KEY}-{NUMBER}', so this sorts by the numeric suffix.
        """
        return self.annotate(key_number=KeyNumber("key")).order_by("key_number")

    def set_status(self, status: IssueStatus) -> int:
        """Bulk update status for all issues in queryset. Returns count of updated rows."""
        return self.update(status=status)

    def move_to_milestone(self, milestone: Milestone | None) -> int:
        """Bulk update milestone for all epics in queryset. Returns count of updated rows."""
        return self.update(milestone=milestone)

    def ordered_by_priority(self) -> IssueQuerySet:
        """Order by priority: critical > high > medium > low, then by key.

        Priority is now on BaseIssue, so we can order directly.
        Uses descending order so higher priority (critical) appears first.
        """

        priority_order = Case(
            *[When(priority=choice[0], then=Value(i)) for i, choice in enumerate(self.model.get_priority_choices())],
            default=Value(-1),
            output_field=IntegerField(),
        )
        return self.annotate(
            priority_order=priority_order,
            key_number=KeyNumber("key"),
        ).order_by("-priority_order", "key_number")

    def get_progress(self):
        """Calculate progress based on descendants' statuses and story points."""
        children = self.only("status", "estimated_points", "project_id")

        todo_weight = 0
        in_progress_weight = 0
        done_weight = 0

        for child in children:
            weight = getattr(child, "estimated_points", None) or 1
            category = child.get_status_category()
            if category == "todo":
                todo_weight += weight
            elif category == "in_progress":
                in_progress_weight += weight
            else:
                done_weight += weight

        total_weight = done_weight + in_progress_weight + todo_weight

        if total_weight == 0:
            return None

        done_pct = round(done_weight / total_weight * 100)
        in_progress_pct = round(in_progress_weight / total_weight * 100)
        todo_pct = 100 - done_pct - in_progress_pct

        return {
            "todo_pct": todo_pct,
            "in_progress_pct": in_progress_pct,
            "done_pct": done_pct,
            "todo_weight": todo_weight,
            "in_progress_weight": in_progress_weight,
            "done_weight": done_weight,
            "total_weight": total_weight,
        }

    def with_progress(self):
        """Annotate issues with progress weights from work item descendants.

        Adds total_estimated_points, total_done_points, total_in_progress_points,
        and total_todo_points annotations by summing work item weights (estimated_points
        or 1) from descendant Story, Bug, and Chore items.

        For Epics, uses path-regex matching to find all descendants.
        For other BaseIssue descendants, filters directly by parent relationship.
        """

        # Get the status categories for filtering
        status_categories = self.model.status_categories

        done_statuses = [s for s, cat in status_categories.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in status_categories.items() if cat == "in_progress"]
        todo_statuses = [s for s, cat in status_categories.items() if cat == "todo"]

        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        if self.model == Story or self.model == Bug or self.model == Chore:
            # For individual work items, use the sprint-based helper
            # This is for cases where we're querying work items directly
            done = _work_item_weight(self.model, done_statuses)
            in_progress = _work_item_weight(self.model, in_progress_statuses)
            total = _work_item_weight(self.model, None)

            return self.annotate(
                total_done_points=done,
                total_in_progress_points=in_progress,
                total_todo_points=total - done - in_progress,
                total_estimated_points=total,
            )

        # For Epics and other BaseIssue models, sum work items using path-regex
        # The path field stores the materialized path for treebeard
        # We need to filter work items that are descendants of each issue

        # First, we need to get the path prefix pattern
        # For root issues (depth=1), descendants match path starting with issue.path/
        # For non-root issues, descendants match path starting with issue.path

        # Since we're annotating on a queryset that might include different issue types,
        # we need a more flexible approach using subqueries

        # For each issue, we need to sum work items where the work item's path
        # starts with the issue's path (and has greater depth)
        # This requires a subquery per issue type

        # Get current issue's path as outer reference

        # Helper to build subquery for each work item model
        def work_item_sum(subquery_model, statuses=None):
            """Build subquery to sum estimated_points for work items."""
            qs = subquery_model.objects.filter(
                project=OuterRef("project"),
            ).filter(
                # Use path regex to find descendants: path starts with issue.path + "/"
                # Treebeard path format: "000100020003/" for depth 3
                path__regex=rf"^{OuterRef('path')}[0-9]{{4}}/",
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

        # Build a combined approach: for each issue, sum all descendant work items
        # by matching path prefix using substring comparison
        # For a given issue with path P, descendants have path starting with P followed by a 4-digit step
        # We use substring matching: path LIKE P + '____/%'

        def descendants_sum(model, statuses=None):
            """Sum work items that are descendants of issues in queryset."""
            qs = model.objects.filter(
                project=OuterRef("project"),
            ).filter(
                # Path starts with this issue's path and has another step
                path__regex=rf"^{OuterRef('path')}[0-9]{{4}}/",
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

        # Add annotations for each status category
        Story = apps.get_model("issues", "Story")
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        qs = self.annotate(
            total_done_points=(
                descendants_sum(Story, done_statuses)
                + descendants_sum(Bug, done_statuses)
                + descendants_sum(Chore, done_statuses)
            ),
            total_in_progress_points=(
                descendants_sum(Story, in_progress_statuses)
                + descendants_sum(Bug, in_progress_statuses)
                + descendants_sum(Chore, in_progress_statuses)
            ),
            total_todo_points=(
                descendants_sum(Story, todo_statuses)
                + descendants_sum(Bug, todo_statuses)
                + descendants_sum(Chore, todo_statuses)
            ),
        )

        # total_estimated_points = done + in_progress + todo
        return qs.annotate(
            total_estimated_points=F("total_done_points") + F("total_in_progress_points") + F("total_todo_points")
        )


class IssueManager(PolymorphicManager):
    """Custom Manager for Issue models."""

    def get_queryset(self) -> IssueQuerySet:
        return IssueQuerySet(self.model, using=self._db)

    def for_project(self, project: Project) -> IssueQuerySet:
        return self.get_queryset().for_project(project)

    def for_workspace(self, workspace: Workspace) -> IssueQuerySet:
        return self.get_queryset().for_workspace(workspace)

    def for_sprint(self, sprint: Sprint) -> IssueQuerySet:
        return self.get_queryset().for_sprint(sprint)

    def for_milestone(self, milestone: Milestone) -> IssueQuerySet:
        return self.get_queryset().for_milestone(milestone)

    def work_items(self) -> IssueQuerySet:
        return self.get_queryset().work_items()

    def done(self) -> IssueQuerySet:
        return self.get_queryset().done()


class MilestoneQuerySet(QuerySet):
    """Custom QuerySet for Milestone model."""

    def for_project(self, project: Project) -> MilestoneQuerySet:
        """Filter milestones by project."""
        return self.filter(project=project)

    def for_workspace(self, workspace: Workspace) -> MilestoneQuerySet:
        """Filter milestones by workspace (through project)."""
        return self.filter(project__workspace=workspace)

    def for_choices(self) -> MilestoneQuerySet:
        """
        Return only the fields needed for form choice fields.
        Use this when populating ModelChoiceField/ModelMultipleChoiceField querysets.
        """
        return self.only("id", "key", "title")

    def with_status(self, status: IssueStatus) -> MilestoneQuerySet:
        """Filter by status."""
        return self.filter(status=status)

    def active(self) -> MilestoneQuerySet:
        """Filter to active milestones (not archived, done, or won't do)."""
        return self.exclude(
            status__in=[self.model.status_model.ARCHIVED, self.model.status_model.DONE, self.model.status_model.WONT_DO]
        )

    def search(self, query: str) -> MilestoneQuerySet:
        """Search milestones by title or key (case-insensitive)."""
        if not query:
            return self
        return self.filter(models.Q(title__icontains=query) | models.Q(key__icontains=query))

    def overdue(self) -> MilestoneQuerySet:
        """Filter to overdue milestones (due_date in the past and not done/archived/won't do)."""
        return self.filter(due_date__lt=timezone.now().date()).exclude(
            status__in=[self.model.status_model.DONE, self.model.status_model.ARCHIVED, self.model.status_model.WONT_DO]
        )

    def with_key(self, key: str, exclude: Milestone | None = None) -> MilestoneQuerySet:
        """Filter by key, optionally excluding a specific instance."""
        qs = self.filter(key=key)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def with_key_prefix(self, prefix: str, exclude: Milestone | None = None) -> MilestoneQuerySet:
        """Filter by key prefix, optionally excluding a specific instance."""
        qs = self.filter(key__startswith=prefix)
        if exclude:
            qs = qs.exclude(pk=exclude.pk)
        return qs

    def with_progress(self) -> MilestoneQuerySet:
        """Annotate milestones with progress from linked epics' work items.

        Adds total_estimated_points, total_done_points, total_in_progress_points,
        and total_todo_points annotations by summing work item weights from all
        epics linked to each milestone.

        The progress is computed from the work items (Story, Bug, Chore) that
        are descendants of the epics linked to the milestone.
        """

        # For each milestone, we sum work items from all its linked epics.
        # Work items are descendants of epics, identified by path prefix matching:
        # work_item.path starts with epic.path + 4-digit step
        # Get epic paths for this milestone and create a combined regex pattern
        # Then filter work items that match this pattern
        # Helper to build subquery that sums work items from epics linked to milestone
        def epic_work_items_sum(model, statuses=None):
            """Sum work items that are descendants of epics linked to milestone.

            Uses path prefix matching: work item path starts with epic.path + step.
            """
            Epic = apps.get_model("issues", "Epic")

            # Get epic paths for this milestone as a subquery
            Epic.objects.filter(milestone=OuterRef("pk")).values("path")

            # Build regex pattern for all epic paths: ^(path1|path2|...)\\d{4}/
            # This requires collecting all epic paths and creating an OR pattern

            # Get the epic paths for correlation
            Epic.objects.filter(milestone=OuterRef("pk")).values("path")

            # Build a subquery with path regex matching
            # Work item is descendant of epic if: work_item.path LIKE epic.path + '____/%'
            # where ____ is exactly 4 digits (treebeard step)

            return Coalesce(
                Subquery(
                    model.objects.filter(
                        project=OuterRef("project"),
                    )
                    .filter(
                        # Match work items that are descendants of epics in this milestone
                        # Work item path starts with epic.path + 4-digit step
                        path__regex=r"^("
                        + r"|".join(
                            rf"\Q{epic['path']}\E"
                            for epic in Epic.objects.filter(milestone=OuterRef("pk")).values("path")[:1]
                        )
                        + r")[0-9]{4}/",
                    )
                    .values("project")
                    .annotate(total=Sum(Coalesce("estimated_points", Value(1))))
                    .values("total")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            )

        # Get status categories
        status_categories = self.model.status_model.status_categories
        done_statuses = [s for s, cat in status_categories.items() if cat == "done"]
        in_progress_statuses = [s for s, cat in status_categories.items() if cat == "in_progress"]
        todo_statuses = [s for s, cat in status_categories.items() if cat == "todo"]

        # Get model classes
        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        Story = apps.get_model("issues", "Story")

        # Annotate with progress from epic work items
        qs = self.annotate(
            total_done_points=(
                epic_work_items_sum(Story, done_statuses)
                + epic_work_items_sum(Bug, done_statuses)
                + epic_work_items_sum(Chore, done_statuses)
            ),
            total_in_progress_points=(
                epic_work_items_sum(Story, in_progress_statuses)
                + epic_work_items_sum(Bug, in_progress_statuses)
                + epic_work_items_sum(Chore, in_progress_statuses)
            ),
            total_todo_points=(
                epic_work_items_sum(Story, todo_statuses)
                + epic_work_items_sum(Bug, todo_statuses)
                + epic_work_items_sum(Chore, todo_statuses)
            ),
        )

        # total_estimated_points = done + in_progress + todo
        return qs.annotate(
            total_estimated_points=F("total_done_points") + F("total_in_progress_points") + F("total_todo_points")
        )

        # This is tricky because we need to match against multiple paths
        # Use a different approach: join epic and work items on path prefix

        # For work items to be descendants of epics in this milestone:
        # work_item.path LIKE epic.path + 4_digits + '/'
        # epic.milestone = current_milestone

        # Use a join-based approach instead
        # Annotate with subqueries that use path matching via substring

        # Since path regex with multiple alternatives is complex, use exists subquery
        # to check if work item is descendant of any epic in this milestone

        def descendants_sum(model, statuses=None):
            """Sum work items that are descendants of epics linked to milestone."""
            qs = model.objects.filter(
                project=OuterRef("pk"),
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

        # Actually, for milestones we can use a simpler approach:
        # Get the epic paths first, then use them to filter work items

        # Let's use the helper function from helpers.py for sprint-based, but for
        # milestones we need path-based matching

        # The key insight is that for epics, we have path-based tree structure
        # Work items (Story, Bug, Chore) are descendants of epics
        # We need to match: work_item.path starts with epic.path + step

        # For a single milestone, we can do:
        # 1. Get epic paths for this milestone
        # 2. Filter work items whose path matches any epic path + step

        # Since we're in a subquery context, use a correlated subquery

        Bug = apps.get_model("issues", "Bug")
        Chore = apps.get_model("issues", "Chore")
        Epic = apps.get_model("issues", "Epic")

        # Get epic path subquery for this milestone
        Epic.objects.filter(milestone=OuterRef("pk")).values("path")

        # Helper to sum work items descending from epics of this milestone
        def epic_work_items_sum(model, statuses=None):
            """Sum work items that are descendants of epics linked to milestone."""
            qs = model.objects.filter(
                project=OuterRef("project"),
            ).filter(
                # Work item is descendant of an epic linked to this milestone
                # path starts with epic.path + 4-digit step
                path__regex=r"^(("
                + "|".join(
                    rf"({epic['path']})" for epic in Epic.objects.filter(milestone=OuterRef("pk")).values("path")[:1]
                )
                + r")[0-9]{{4}}/)",
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

        # Simplified: use a single subquery with EXISTS to check if work item
        # is descendant of any epic in this milestone
        Epic.objects.filter(
            milestone=OuterRef("pk"),
        ).filter(
            # Work item path starts with epic path + step
            models.Q()  # Placeholder for path matching
        )

        # Actually, for simplicity and correctness, use a different approach:
        # Join epic and work items, then aggregate by milestone

        # Get epic paths for this milestone
        Epic.objects.filter(milestone=OuterRef("pk")).values("path")

        # Build regex pattern for all epic paths
        # Each epic path + 4-digit step = pattern

        # For each work item model, sum estimated_points where work item is descendant
        # of an epic linked to this milestone

        # Use path prefix matching: work_item.path LIKE epic.path + '____/%'
        # Where ____ is exactly 4 digits (treebeard step)

        # For progress calculation, we need to sum work items from epics linked to milestone
        # Use the issue path regex pattern

        # Since this is complex with multiple OR conditions, use a simpler approach:
        # Join epic and work items on path prefix, then aggregate

        # Get epic paths subquery
        Epic.objects.filter(milestone=OuterRef("pk")).values("path")

        # Helper function using path regex
        def epic_work_items_sum(model, statuses=None):
            """Sum work items that are descendants of epics linked to milestone."""
            # Match work items whose path starts with any epic's path + step
            # Using a subquery to get epic paths and matching

            # Since we can't easily create OR regex patterns in subqueries,
            # use EXISTS to check if work item is descendant of any epic
            Epic.objects.filter(milestone=OuterRef("pk"))

            # For work item to be descendant: work_item.path starts with epic.path + step
            # This requires path prefix matching

            # Use substring matching: work_item.path LIKE epic.path + 4digits + '/'
            # Since epic path varies, use a different approach

            # Get epic path as subquery, then use regex matching
            Epic.objects.filter(milestone=OuterRef("pk")).values("path")[:1]

            # Match path: starts with epic.path followed by exactly 4 digits then /
            # path regex: ^epic_path\d{4}/

            # For multiple epics, we need OR logic which is complex in SQL
            # Use a simpler approach: join epic with work items on path prefix

            return Coalesce(
                Subquery(
                    model.objects.filter(
                        project=OuterRef("project"),
                    )
                    .filter(
                        # Use path regex withOuterRef to match epic path prefix
                        # This is tricky - we need the epic path as a value
                        path__regex=r"^(("
                        + r"|".join(
                            rf"\Q{epic['path']}\E"
                            for epic in Epic.objects.filter(milestone=OuterRef("pk")).values("path")[:1]
                        )
                        + r")[0-9]{4}/)",
                    )
                    .values("project")
                    .annotate(total=Sum(Coalesce("estimated_points", Value(1))))
                    .values("total")[:1],
                    output_field=IntegerField(),
                ),
                Value(0),
            )

        # Let me simplify this significantly
        # For milestones, the progress comes from linked epics' work items
        # Use the existing issue path-based approach but adapted for milestone context

        # Get epic paths for this milestone
        Epic.objects.filter(milestone=OuterRef("pk")).values("path")

        # For progress, sum work items from epics where epic.milestone = current
        # Work items are descendants of epics (path starts with epic.path + step)

        # Simpler approach: use path prefix matching with subquery for epic paths
        # Since we're in a subquery context, we need to correlate properly

        def epic_work_items_sum(model, statuses=None):
            """Sum work items that are descendants of epics linked to milestone."""
            # Join work items with epics on path prefix
            # epic.milestone = current_milestone AND work_item.path LIKE epic.path + step

            # Use a join approach with subquery
            epic_alias = Epic.objects.filter(milestone=OuterRef("pk")).values("path")[:1]

            qs = model.objects.filter(
                project=OuterRef("project"),
            ).filter(
                # Work item path starts with epic.path + 4-digit step
                # epic.milestone = current milestone
                path__regex=rf"^{epic_alias}[0-9]{{4}}/",
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

        # Annotate with progress from epic work items
        return self.annotate(
            total_done_points=(
                epic_work_items_sum(Story, done_statuses)
                + epic_work_items_sum(Bug, done_statuses)
                + epic_work_items_sum(Chore, done_statuses)
            ),
            total_in_progress_points=(
                epic_work_items_sum(Story, in_progress_statuses)
                + epic_work_items_sum(Bug, in_progress_statuses)
                + epic_work_items_sum(Chore, in_progress_statuses)
            ),
            total_todo_points=(
                epic_work_items_sum(Story, todo_statuses)
                + epic_work_items_sum(Bug, todo_statuses)
                + epic_work_items_sum(Chore, todo_statuses)
            ),
        ).annotate(
            total_estimated_points=F("total_done_points") + F("total_in_progress_points") + F("total_todo_points")
        )


class MilestoneManager(models.Manager):
    """Custom Manager for Milestone model."""

    def get_queryset(self) -> MilestoneQuerySet:
        return MilestoneQuerySet(self.model, using=self._db)

    def for_project(self, project: Project) -> MilestoneQuerySet:
        return self.get_queryset().for_project(project)

    def for_workspace(self, workspace: Workspace) -> MilestoneQuerySet:
        return self.get_queryset().for_workspace(workspace)
