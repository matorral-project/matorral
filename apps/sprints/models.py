import re

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.sprints.managers import SprintManager
from apps.utils.models import BaseModel
from apps.workspaces.models import Workspace

from auditlog.registry import auditlog

User = get_user_model()


class SprintStatus(models.TextChoices):
    PLANNING = "planning", _("Planning")
    ACTIVE = "active", _("Active")
    COMPLETED = "completed", _("Completed")
    ARCHIVED = "archived", _("Archived")


@auditlog.register(
    include_fields=[
        "key",
        "name",
        "goal",
        "status",
        "start_date",
        "end_date",
        "owner",
        "capacity",
    ]
)
class Sprint(BaseModel):
    """
    A sprint is a time-boxed iteration for agile development.
    Sprints are workspace-scoped and can contain work items from any project in that workspace.
    """

    workspace = models.ForeignKey(
        Workspace,
        verbose_name=_("Workspace"),
        on_delete=models.CASCADE,
        related_name="sprints",
    )
    key = models.CharField(
        _("Key"),
        max_length=50,
        db_index=True,
        blank=True,
        help_text=_("Auto-generated unique identifier (e.g., SPRINT-1)."),
    )
    name = models.CharField(_("Name"), max_length=255, db_index=True)
    goal = models.TextField(_("Goal"), blank=True, help_text=_("The sprint goal or objective."))
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=SprintStatus.choices,
        default=SprintStatus.PLANNING,
        db_index=True,
    )
    start_date = models.DateField(_("Start Date"), db_index=True)
    end_date = models.DateField(_("End Date"), db_index=True)
    owner = models.ForeignKey(
        User,
        verbose_name=_("Owner"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_sprints",
    )
    created_by = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_sprints",
    )

    # Velocity tracking
    capacity = models.PositiveIntegerField(
        _("Capacity"),
        null=True,
        blank=True,
        help_text=_("Planned capacity in story points."),
    )
    committed_points = models.PositiveIntegerField(
        _("Committed Points"),
        default=0,
        help_text=_("Total points committed at sprint start."),
    )
    completed_points = models.PositiveIntegerField(
        _("Completed Points"),
        default=0,
        help_text=_("Total points completed."),
    )

    objects = SprintManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"],
                name="unique_sprint_key_per_workspace",
            ),
            models.UniqueConstraint(
                fields=["workspace"],
                condition=models.Q(status="active"),
                name="unique_active_sprint_per_workspace",
            ),
        ]
        ordering = ["-start_date", "name"]
        verbose_name = _("Sprint")
        verbose_name_plural = _("Sprints")

    def __str__(self):
        return f"[{self.key}] {self.name}"

    def save(self, *args, **kwargs):
        if self.key:
            self.key = self.key.strip().upper()
        else:
            self.key = self._generate_unique_key()
        super().save(*args, **kwargs)

    def clean(self):
        """Validate sprint dates and constraints."""
        super().clean()
        if self.start_date and self.end_date:
            if self.end_date <= self.start_date:
                raise ValidationError(_("End date must be after start date."))
            # Validate duration is between 1 and 8 weeks
            duration_days = (self.end_date - self.start_date).days
            if duration_days < 7:
                raise ValidationError(_("Sprint duration must be at least 1 week."))
            if duration_days > 56:
                raise ValidationError(_("Sprint duration cannot exceed 8 weeks."))

    def _generate_unique_key(self) -> str:
        """
        Generate a unique key for this sprint within its workspace.
        Format: SPRINT-{NUMBER} (e.g., SPRINT-1, SPRINT-2)
        """
        prefix = "SPRINT-"
        existing_keys = (
            Sprint.objects.for_workspace(self.workspace)
            .with_key_prefix(prefix, exclude=self if self.pk else None)
            .values_list("key", flat=True)
        )

        # Extract numeric suffixes and find max
        max_num = 0
        pattern = re.compile(r"^SPRINT-(\d+)$")

        for key in existing_keys:
            match = pattern.match(key)
            if match:
                max_num = max(max_num, int(match.group(1)))

        return f"SPRINT-{max_num + 1}"

    def get_absolute_url(self):
        return reverse(
            "sprints:sprint_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": self.key,
            },
        )

    @property
    def duration_weeks(self) -> int:
        """Return the sprint duration in weeks."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days // 7
        return 0

    @property
    def velocity_percentage(self) -> int:
        """Return completed points as a percentage of committed points."""
        if self.committed_points > 0:
            return int((self.completed_points / self.committed_points) * 100)
        return 0

    def can_start(self) -> bool:
        """Check if this sprint can be started (no other active sprint in workspace)."""
        if self.status != SprintStatus.PLANNING:
            return False
        return not Sprint.objects.for_workspace(self.workspace).active().exclude(pk=self.pk).exists()

    def get_next_sprint(self):
        """Find the next planning sprint for issue rollover."""
        return (
            Sprint.objects.for_workspace(self.workspace)
            .planning()
            .filter(start_date__gt=self.end_date)
            .order_by("start_date")
            .first()
        )

    def calculate_committed_points(self) -> int:
        """Sum estimated_points from all assigned work items."""
        from django.db.models import Sum

        from apps.issues.models import Bug, Chore, Story

        total = 0
        for model in [Story, Bug, Chore]:
            result = model.objects.filter(sprint=self).aggregate(total=Sum("estimated_points"))
            total += result["total"] or 0
        return total

    def calculate_completed_points(self) -> int:
        """Sum points from done/archived work items."""
        from django.db.models import Sum

        from apps.issues.models import Bug, Chore, IssueStatus, Story

        done_statuses = [IssueStatus.DONE, IssueStatus.ARCHIVED]
        total = 0
        for model in [Story, Bug, Chore]:
            result = model.objects.filter(sprint=self, status__in=done_statuses).aggregate(
                total=Sum("estimated_points")
            )
            total += result["total"] or 0
        return total

    def update_velocity(self):
        """Recalculate and save committed/completed points."""
        self.committed_points = self.calculate_committed_points()
        self.completed_points = self.calculate_completed_points()
        self.save(update_fields=["committed_points", "completed_points", "updated_at"])
