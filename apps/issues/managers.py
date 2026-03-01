from typing import TYPE_CHECKING

from django.db import models
from django.db.models import Case, Func, IntegerField, QuerySet, Value, When
from django.utils import timezone

from apps.issues.utils import get_cached_content_type

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
        """Filter to work items assigned to a sprint.

        Uses Django's reverse OneToOne relations from BaseIssue to its subclasses
        to filter by the sprint FK (which lives on the subclass tables via WorkItemMixin).
        """
        return self.filter(
            models.Q(story__sprint=sprint) | models.Q(bug__sprint=sprint) | models.Q(chore__sprint=sprint)
        )

    def backlog(self) -> IssueQuerySet:
        """Filter to work items NOT assigned to any sprint.

        Returns only work items (Story, Bug, Chore) that have no sprint.
        Epics don't have sprints and are excluded from this filter.
        """
        from apps.issues.models import Bug, Chore, Story

        # Get work items and exclude those that have a sprint assigned.
        # Since sprint is on each subclass, we need to exclude based on each relation.
        return (
            self.instance_of(Story, Bug, Chore)
            .exclude(story__sprint__isnull=False)
            .exclude(bug__sprint__isnull=False)
            .exclude(chore__sprint__isnull=False)
        )

    def of_type(self, *types: type) -> IssueQuerySet:
        """Filter to specific issue types."""
        return self.instance_of(*types)

    def work_items(self) -> IssueQuerySet:
        """Filter to work items only (Story, Bug, Chore)."""
        from apps.issues.models import Bug, Chore, Story

        return self.instance_of(Story, Bug, Chore)

    def roots(self) -> IssueQuerySet:
        """Filter to root-level issues (no parent)."""
        return self.filter(depth=1)

    def with_status(self, status: IssueStatus) -> IssueQuerySet:
        """Filter by status."""
        return self.filter(status=status)

    def active(self) -> IssueQuerySet:
        """Filter to active issues (not archived, done, or won't do)."""
        from apps.issues.models import IssueStatus

        return self.exclude(status__in=[IssueStatus.ARCHIVED, IssueStatus.DONE, IssueStatus.WONT_DO])

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
        from apps.issues.models import IssueStatus

        return self.filter(due_date__lt=timezone.now().date()).exclude(
            status__in=[IssueStatus.DONE, IssueStatus.ARCHIVED, IssueStatus.WONT_DO]
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
        from apps.issues.models import IssuePriority

        priority_order = Case(
            *[When(priority=choice[0], then=Value(i)) for i, choice in enumerate(IssuePriority.choices)],
            default=Value(-1),
            output_field=IntegerField(),
        )
        return self.annotate(
            priority_order=priority_order,
            key_number=KeyNumber("key"),
        ).order_by("-priority_order", "key_number")


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
        from apps.issues.models import IssueStatus

        return self.exclude(status__in=[IssueStatus.ARCHIVED, IssueStatus.DONE, IssueStatus.WONT_DO])

    def search(self, query: str) -> MilestoneQuerySet:
        """Search milestones by title or key (case-insensitive)."""
        if not query:
            return self
        return self.filter(models.Q(title__icontains=query) | models.Q(key__icontains=query))

    def overdue(self) -> MilestoneQuerySet:
        """Filter to overdue milestones (due_date in the past and not done/archived/won't do)."""
        from apps.issues.models import IssueStatus

        return self.filter(due_date__lt=timezone.now().date()).exclude(
            status__in=[IssueStatus.DONE, IssueStatus.ARCHIVED, IssueStatus.WONT_DO]
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


class MilestoneManager(models.Manager):
    """Custom Manager for Milestone model."""

    def get_queryset(self) -> MilestoneQuerySet:
        return MilestoneQuerySet(self.model, using=self._db)

    def for_project(self, project: Project) -> MilestoneQuerySet:
        return self.get_queryset().for_project(project)

    def for_workspace(self, workspace: Workspace) -> MilestoneQuerySet:
        return self.get_queryset().for_workspace(workspace)


class SubtaskQuerySet(QuerySet):
    """Custom QuerySet for Subtask model."""

    def for_parent(self, parent: BaseIssue) -> SubtaskQuerySet:
        """Filter subtasks for a specific parent issue."""
        content_type = get_cached_content_type(type(parent))
        return self.filter(content_type=content_type, object_id=parent.pk)


class SubtaskManager(models.Manager):
    """Custom Manager for Subtask model."""

    def get_queryset(self) -> SubtaskQuerySet:
        return SubtaskQuerySet(self.model, using=self._db)

    def for_parent(self, parent: BaseIssue) -> SubtaskQuerySet:
        return self.get_queryset().for_parent(parent)
