import re

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.issues.managers import IssueManager, MilestoneManager, SubtaskManager
from apps.projects.models import Project
from apps.utils.models import BaseModel

from auditlog.registry import auditlog
from polymorphic.models import PolymorphicModel
from treebeard.mp_tree import MP_Node

User = get_user_model()


class IssueStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    PLANNING = "planning", _("Planning")
    READY = "ready", _("Ready")
    IN_PROGRESS = "in_progress", _("In Progress")
    BLOCKED = "blocked", _("Blocked")
    IN_REVIEW = "in_review", _("In Review")
    DONE = "done", _("Done")
    WONT_DO = "wont_do", _("Won't Do")
    ARCHIVED = "archived", _("Archived")


STATUS_CATEGORIES = {
    IssueStatus.DRAFT: "todo",
    IssueStatus.PLANNING: "todo",
    IssueStatus.READY: "todo",
    IssueStatus.IN_PROGRESS: "in_progress",
    IssueStatus.BLOCKED: "in_progress",
    IssueStatus.IN_REVIEW: "in_progress",
    IssueStatus.DONE: "done",
    IssueStatus.WONT_DO: "done",
    IssueStatus.ARCHIVED: "done",
}


class IssuePriority(models.TextChoices):
    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")
    CRITICAL = "critical", _("Critical")


class BugSeverity(models.TextChoices):
    TRIVIAL = "trivial", _("Trivial")
    MINOR = "minor", _("Minor")
    MAJOR = "major", _("Major")
    CRITICAL = "critical", _("Critical")
    BLOCKER = "blocker", _("Blocker")


@auditlog.register(
    include_fields=[
        "key",
        "title",
        "description",
        "status",
        "due_date",
        "owner",
        "priority",
    ]
)
class Milestone(BaseModel):
    """
    A milestone marks a significant project-level checkpoint.
    Milestones belong to a project and epics within that project can be linked to them.
    """

    project = models.ForeignKey(
        Project,
        verbose_name=_("Project"),
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    key = models.CharField(
        _("Key"),
        max_length=50,
        db_index=True,
        blank=True,
        help_text=_("Auto-generated unique identifier (e.g., M-1)."),
    )
    title = models.CharField(_("Title"), max_length=255, db_index=True)
    description = models.TextField(_("Description"), blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=IssueStatus.choices,
        default=IssueStatus.DRAFT,
        db_index=True,
    )
    due_date = models.DateField(_("Due Date"), null=True, blank=True, db_index=True)
    owner = models.ForeignKey(
        User,
        verbose_name=_("Owner"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_milestones",
    )
    created_by = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_milestones",
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=IssuePriority.choices,
        default=IssuePriority.MEDIUM,
        db_index=True,
    )

    objects = MilestoneManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "key"],
                name="unique_milestone_key_per_project",
            ),
        ]
        ordering = ["due_date", "title"]
        verbose_name = _("Milestone")
        verbose_name_plural = _("Milestones")

    def __str__(self):
        return f"[{self.key}] {self.title}"

    def save(self, *args, **kwargs):
        if self.key:
            self.key = self.key.strip().upper()
        else:
            self.key = self._generate_unique_key()
        super().save(*args, **kwargs)

    def _generate_unique_key(self) -> str:
        """
        Generate a unique key for this milestone within its project.
        Format: M-{NUMBER} (e.g., M-1, M-2)
        """
        prefix = "M-"
        existing_keys = (
            Milestone.objects.for_project(self.project)
            .with_key_prefix(prefix, exclude=self if self.pk else None)
            .values_list("key", flat=True)
        )

        # Extract numeric suffixes and find max
        max_num = 0
        pattern = re.compile(r"^M-(\d+)$")

        for key in existing_keys:
            match = pattern.match(key)
            if match:
                max_num = max(max_num, int(match.group(1)))

        return f"M-{max_num + 1}"

    def get_absolute_url(self):
        return reverse(
            "milestones:milestone_detail",
            kwargs={
                "workspace_slug": self.project.workspace.slug,
                "project_key": self.project.key,
                "key": self.key,
            },
        )


class BaseIssue(MP_Node, PolymorphicModel):
    """
    Base issue model using Materialized Path tree and polymorphic inheritance.
    All issue types (Epic, Story, Bug, Chore) inherit from this.
    """

    project = models.ForeignKey(
        Project,
        verbose_name=_("Project"),
        on_delete=models.CASCADE,
        related_name="issues",
    )
    key = models.CharField(
        _("Key"),
        max_length=50,
        db_index=True,
        blank=True,
        help_text=_("Auto-generated unique identifier (e.g., PROJ-1-123)."),
    )
    title = models.CharField(_("Title"), max_length=255, db_index=True)
    description = models.TextField(_("Description"), blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=IssueStatus.choices,
        default=IssueStatus.DRAFT,
        db_index=True,
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=IssuePriority.choices,
        default=IssuePriority.MEDIUM,
        db_index=True,
    )
    # Note: estimated_points lives on BaseIssue (not on WorkItemMixin) so that treebeard
    # tree queries across all issue types can access points in a single query without
    # extra JOINs. Epics inherit this field but should NOT use it directly — epic "points"
    # are always the sum of their children's points, calculated via get_progress().
    estimated_points = models.PositiveIntegerField(
        _("Estimated Points"),
        null=True,
        blank=True,
        help_text=_("Story points or effort estimate. Only meaningful on work items (Story, Bug, Chore)."),
    )
    due_date = models.DateField(_("Due Date"), null=True, blank=True, db_index=True)
    assignee = models.ForeignKey(
        User,
        verbose_name=_("Assignee"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_issues",
    )
    created_by = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_issues",
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    # Note: We intentionally do NOT set node_order_by here.
    # Using node_order_by forces sorted positions for move() operations,
    # which can cause path conflicts when the tree paths don't match the sorted order.
    # Sorting is handled at query time via ordered_by_key() instead.

    objects = IssueManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "key"],
                name="unique_issue_key_per_project",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "polymorphic_ctype"]),
        ]
        ordering = ["path"]
        verbose_name = _("Issue")
        verbose_name_plural = _("Issues")

    def __str__(self):
        return f"[{self.key}] {self.title}"

    def save(self, *args, **kwargs):
        if self.key:
            self.key = self.key.strip().upper()
        else:
            self.key = self._generate_unique_key()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate parent type constraints for each issue type."""
        super().clean()
        # Only validate parent type if the object is already in the tree (has a path)
        # New objects are added via add_child/add_root which sets the path
        if self.path:
            self._validate_parent_type()

    def _validate_parent_type(self):
        """Subclasses override to enforce parent type constraints."""
        pass

    def _generate_unique_key(self) -> str:
        """
        Generate a unique key for this issue within its project.
        Format: {PROJECT_KEY}-{NUMBER} (e.g., PROJ-1-123)
        """
        project_key = self.project.key
        prefix = f"{project_key}-"

        # Get all matching keys for this project
        qs = BaseIssue.objects.for_project(self.project).filter(key__startswith=prefix)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        existing_keys = qs.values_list("key", flat=True)

        # Extract numeric suffixes and find max
        max_num = 0
        pattern = re.compile(rf"^{re.escape(project_key)}-(\d+)$")

        for key in existing_keys:
            match = pattern.match(key)
            if match:
                max_num = max(max_num, int(match.group(1)))

        return f"{project_key}-{max_num + 1}"

    def get_absolute_url(self):
        return reverse(
            "issues:issue_detail",
            kwargs={
                "workspace_slug": self.project.workspace.slug,
                "project_key": self.project.key,
                "key": self.key,
            },
        )

    def get_issue_type(self) -> str:
        """Return the issue type name (e.g., 'milestone', 'story')."""
        return self.__class__.__name__.lower()

    def get_issue_type_display(self) -> str:
        """Return the human-readable issue type name."""
        return self.__class__._meta.verbose_name.title()

    def get_parent_issue(self):
        """Return the parent issue, or None if this is a root issue."""
        parent = self.get_parent()
        return parent

    def get_children_issues(self):
        """Return all direct children of this issue, ordered by key."""
        from apps.issues.managers import KeyNumber

        return self.get_children().annotate(key_number=KeyNumber("key")).order_by("key_number")

    def get_descendant_issues(self):
        """Return all descendants of this issue."""
        return self.get_descendants()

    def get_ancestor_issues(self):
        """Return all ancestors of this issue."""
        return self.get_ancestors()

    def get_progress(self):
        """Calculate progress based on descendants' statuses and story points."""
        from apps.issues.helpers import calculate_progress

        children = self.get_descendants().non_polymorphic().only("status", "estimated_points")
        return calculate_progress(children)


@auditlog.register(
    include_fields=[
        "key",
        "title",
        "description",
        "status",
        "due_date",
        "assignee",
        "priority",
        "milestone",
    ]
)
class Epic(BaseIssue):
    """
    An epic is a large body of work that can be broken down into stories.
    Epics are root-level issues and can be linked to a project-level milestone.
    """

    milestone = models.ForeignKey(
        Milestone,
        verbose_name=_("Milestone"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="epics",
        help_text=_("Optionally link this epic to a project-level milestone."),
    )

    class Meta:
        verbose_name = _("Epic")
        verbose_name_plural = _("Epics")

    def clean(self):
        """Validate that milestone belongs to the same project as this epic."""
        super().clean()
        if self.milestone and self.milestone.project_id != self.project_id:
            raise ValidationError(_("Milestone must belong to the same project as the Epic."))

    def _validate_parent_type(self):
        """Epics must be root-level issues (no tree parent allowed)."""
        parent = self.get_parent()
        if parent is not None:
            raise ValidationError(_("Epics cannot have a parent issue."))


class WorkItemMixin(models.Model):
    """
    Abstract mixin for work items (Story, Bug, Chore).
    Adds sprint field. Priority and estimated_points are now on BaseIssue.
    """

    sprint = models.ForeignKey(
        "sprints.Sprint",
        verbose_name=_("Sprint"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_items",
    )

    class Meta:
        abstract = True


@auditlog.register(
    include_fields=[
        "key",
        "title",
        "description",
        "status",
        "due_date",
        "assignee",
        "priority",
        "estimated_points",
        "sprint",
    ]
)
class Story(WorkItemMixin, BaseIssue):
    """
    A story represents a user requirement or feature.
    Parent can be an Epic or no parent (root).
    """

    class Meta:
        verbose_name = _("Story")
        verbose_name_plural = _("Stories")

    def _validate_parent_type(self):
        """Stories can only have Epic parents or be root."""
        parent = self.get_parent()
        if parent is not None and not isinstance(parent, Epic):
            raise ValidationError(_("Stories can only be children of Epics."))


@auditlog.register(
    include_fields=[
        "key",
        "title",
        "description",
        "status",
        "due_date",
        "assignee",
        "priority",
        "estimated_points",
        "sprint",
        "severity",
    ]
)
class Bug(WorkItemMixin, BaseIssue):
    """
    A bug represents a defect or issue to be fixed.
    Parent can be an Epic or no parent (root).
    """

    severity = models.CharField(
        _("Severity"),
        max_length=20,
        choices=BugSeverity.choices,
        default=BugSeverity.MINOR,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Bug")
        verbose_name_plural = _("Bugs")

    def _validate_parent_type(self):
        """Bugs can only have Epic parents or be root."""
        parent = self.get_parent()
        if parent is not None and not isinstance(parent, Epic):
            raise ValidationError(_("Bugs can only be children of Epics."))


@auditlog.register(
    include_fields=[
        "key",
        "title",
        "description",
        "status",
        "due_date",
        "assignee",
        "priority",
        "estimated_points",
        "sprint",
    ]
)
class Chore(WorkItemMixin, BaseIssue):
    """
    A chore represents technical or maintenance work.
    Parent can be an Epic or no parent (root).
    """

    class Meta:
        verbose_name = _("Chore")
        verbose_name_plural = _("Chores")

    def _validate_parent_type(self):
        """Chores can only have Epic parents or be root."""
        parent = self.get_parent()
        if parent is not None and not isinstance(parent, Epic):
            raise ValidationError(_("Chores can only be children of Epics."))


class SubtaskStatus(models.TextChoices):
    TODO = "todo", _("To Do")
    IN_PROGRESS = "in_progress", _("In Progress")
    DONE = "done", _("Done")
    WONT_DO = "wont_do", _("Won't Do")


class Subtask(BaseModel):
    """
    A subtask belongs to a work item (Story, Bug, Chore, Issue). Max 20 per parent.
    Subtasks are simple checklist-style items to break down work into smaller actionable items.
    """

    # GenericForeignKey to parent work item
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=models.Q(app_label="issues", model__in=["story", "bug", "chore"]),
    )
    object_id = models.PositiveIntegerField()
    parent = GenericForeignKey("content_type", "object_id")

    title = models.CharField(_("Title"), max_length=255)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=SubtaskStatus.choices,
        default=SubtaskStatus.TODO,
        db_index=True,
    )
    position = models.PositiveIntegerField(_("Position"), default=0, db_index=True)

    objects = SubtaskManager()

    class Meta:
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        verbose_name = _("Subtask")
        verbose_name_plural = _("Subtasks")

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.title:
            self.title = self.title.strip()
        super().save(*args, **kwargs)
