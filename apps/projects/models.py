import re

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import F, Func, Value
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.projects.managers import ProjectQuerySet
from apps.utils.models import BaseModel
from apps.workspaces.models import Workspace

from auditlog.registry import auditlog

User = get_user_model()


class ProjectStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ACTIVE = "active", _("Active")
    COMPLETED = "completed", _("Completed")
    ARCHIVED = "archived", _("Archived")


def generate_project_key(name: str, length: int = 3) -> str:
    """
    Generate a project key from the project name.

    For multi-word names: takes the first ASCII letter of each word.
    For single-word names: takes the first N ASCII letters (controlled by length param).
    Only ASCII letters (A-Z) are used in the key.

    Args:
        name: The project name to generate a key from.
        length: Number of characters to extract for single-word names (default 3).

    Returns:
        An uppercase key string containing only ASCII letters (A-Z).
    """
    # Strip non-ASCII letters from each word and take the first letter
    words = [re.sub(r"[^A-Za-z]", "", word) for word in name.split()]
    words = [w for w in words if w]  # Remove empty strings

    if len(words) > 1:
        # Multi-word: take first letter of each word (up to 6)
        key = "".join(word[0] for word in words[:6])
    elif words:
        # Single word: take first N letters
        key = words[0][:length]
    else:
        # Fallback if no ASCII letters in name
        key = "PRJ"

    return key.upper()


@auditlog.register(include_fields=["name", "key", "description", "status", "lead"])
class Project(BaseModel):
    """
    A project belongs to a workspace.
    """

    workspace = models.ForeignKey(
        Workspace,
        verbose_name=_("Workspace"),
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(_("Name"), max_length=100, db_index=True)
    key = models.CharField(
        _("Key"),
        max_length=6,
        db_index=True,
        blank=True,
        help_text=_("A short unique identifier for the project (e.g., PRJ, DEMO). Auto-generated if not provided."),
    )
    description = models.TextField(_("Description"), blank=True)
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
        db_index=True,
    )
    lead = models.ForeignKey(
        User,
        verbose_name=_("Lead"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_projects",
    )
    created_by = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )

    objects = ProjectQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "key"],
                name="unique_key_per_workspace",
            ),
        ]
        indexes = [
            models.Index(fields=["workspace"]),
        ]
        ordering = ["name"]
        verbose_name = _("Project")
        verbose_name_plural = _("Projects")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.key:
            self.key = self.key.strip().upper()
        else:
            self.key = self._generate_unique_key()
        super().save(*args, **kwargs)

    def _generate_unique_key(self) -> str:
        """
        Generate a unique key for this project within its workspace.

        Keys contain only ASCII letters (A-Z), no numbers or dashes.
        For single-word names, starts with 3 characters and increases length
        up to 6 if needed to find a unique key.
        """
        # Get all existing keys in the workspace (one query)
        qs = Project.objects.for_workspace(self.workspace)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        existing_keys = set(qs.values_list("key", flat=True))

        # For multi-word names, try the initials first
        words = [re.sub(r"[^A-Za-z]", "", word) for word in self.name.split()]
        words = [w for w in words if w]
        is_multi_word = len(words) > 1

        if is_multi_word:
            # Multi-word: use initials (up to 6 letters)
            key = generate_project_key(self.name)
            if key not in existing_keys:
                return key
            # If initials are taken, fall through to length-based approach
            # using the full concatenated words
            base_letters = "".join(words).upper()
        else:
            # Single word: extract all ASCII letters
            base_letters = (words[0] if words else "PRJ").upper()

        # Try increasing lengths from 3 to 6
        for length in range(3, 7):
            key = base_letters[:length]
            if key not in existing_keys:
                return key

        # All lengths exhausted, append a letter suffix (A-Z)
        base_key = base_letters[:5]  # Leave room for suffix
        for suffix in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            key = f"{base_key}{suffix}"
            if key not in existing_keys:
                return key

        # Extremely unlikely fallback: use base + AA, AB, etc.
        base_key = base_letters[:4]
        for first in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            for second in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                key = f"{base_key}{first}{second}"
                if key not in existing_keys:
                    return key

        # This should never happen in practice
        raise ValueError("Unable to generate unique project key")

    def get_absolute_url(self):
        return reverse(
            "projects:project_detail",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "key": self.key,
            },
        )

    def move(self, target_workspace):
        """
        Move this project to a different workspace.

        - If the project key conflicts in the target workspace, a new unique key is generated.
        - All issue keys (format: {PROJECT_KEY}-{N}) are updated if the key changes.
        - Sprint assignments are removed from all work items (sprints are workspace-scoped).
        """
        from apps.issues.models import BaseIssue, Bug, Chore, Story

        old_key = self.key

        key_taken = Project.objects.filter(workspace=target_workspace).exclude(pk=self.pk).filter(key=old_key).exists()

        if key_taken:
            original_workspace = self.workspace
            self.workspace = target_workspace
            new_key = self._generate_unique_key()
            self.workspace = original_workspace
        else:
            new_key = old_key

        if old_key != new_key:
            BaseIssue.objects.filter(project=self).update(
                key=Func(F("key"), Value(f"{old_key}-"), Value(f"{new_key}-"), function="REPLACE")
            )

        Story.objects.filter(project=self).update(sprint=None)
        Bug.objects.filter(project=self).update(sprint=None)
        Chore.objects.filter(project=self).update(sprint=None)

        self.workspace = target_workspace
        self.key = new_key
        self.save()
