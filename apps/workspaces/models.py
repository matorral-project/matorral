import logging
import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.utils.models import BaseModel

from waffle import get_setting
from waffle.models import CACHE_EMPTY, AbstractUserFlag
from waffle.utils import get_cache, keyfmt

from . import roles as workspace_roles
from .context import EmptyWorkspaceContextException, get_current_workspace
from .managers import WorkspaceQuerySet


class WorkspaceScopedManager(models.Manager):
    """Model manager that automatically filters the queryset using the workspace from the global
    workspace context. If no workspace is set, returns an empty queryset."""

    def get_queryset(self):
        queryset = super().get_queryset()
        workspace = get_current_workspace()
        if workspace is None:
            if getattr(settings, "STRICT_WORKSPACE_CONTEXT", False):
                raise EmptyWorkspaceContextException("Workspace missing from context")
            else:
                logging.warning("Workspace not available in filtered context. Use `set_current_workspace()`.")
            return queryset.none()
        return queryset.filter(workspace=workspace)


class BaseWorkspaceModel(BaseModel):
    """Abstract model for objects that belong to a workspace."""

    workspace = models.ForeignKey(
        "workspaces.Workspace",
        verbose_name=_("Workspace"),
        on_delete=models.CASCADE,
    )

    # Default unfiltered manager
    objects = models.Manager()

    # Pre-filtered to the current workspace
    for_workspace = WorkspaceScopedManager()

    class Meta:
        abstract = True


class Workspace(BaseModel):
    """
    A Workspace is the top-level organizational unit.
    """

    objects = WorkspaceQuerySet.as_manager()

    name = models.CharField(_("Name"), max_length=100, db_index=True)
    slug = models.SlugField(_("Slug"), max_length=50, unique=True)
    description = models.TextField(_("Description"), blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        related_name="workspaces",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("Workspace")
        verbose_name_plural = _("Workspaces")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("workspaces:home", kwargs={"workspace_slug": self.slug})

    @property
    def sorted_memberships(self):
        return self.membership_set.order_by("user__email")

    def pending_invitations(self):
        return self.invitations.filter(is_accepted=False)

    @property
    def email(self):
        membership = self.membership_set.filter(role=workspace_roles.ROLE_ADMIN).first()
        return membership.user.email if membership else None


class Membership(BaseModel):
    """A user's workspace membership."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workspace_memberships",
    )
    role = models.CharField(max_length=100, choices=workspace_roles.ROLE_CHOICES)

    def __str__(self):
        return f"{self.user}: {self.workspace}"

    def is_admin(self) -> bool:
        return self.role == workspace_roles.ROLE_ADMIN

    class Meta:
        unique_together = ("workspace", "user")


class Invitation(BaseModel):
    """An invitation for new workspace members."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(
        max_length=100,
        choices=workspace_roles.ROLE_CHOICES,
        default=workspace_roles.ROLE_MEMBER,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_workspace_invitations",
    )
    is_accepted = models.BooleanField(default=False)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accepted_workspace_invitations",
        null=True,
        blank=True,
    )

    def get_url(self) -> str:
        from apps.landing_pages.meta import absolute_url

        return absolute_url(reverse("workspaces:accept_invitation", args=[self.id]))


class Flag(AbstractUserFlag):
    """Custom Waffle flag to support usage with workspaces.

    See https://waffle.readthedocs.io/en/stable/types/flag.html#custom-flag-models"""

    FLAG_WORKSPACES_CACHE_KEY = "FLAG_WORKSPACES_CACHE_KEY"
    FLAG_WORKSPACES_CACHE_KEY_DEFAULT = "flag:%s:workspaces"

    workspaces = models.ManyToManyField(
        "workspaces.Workspace",
        blank=True,
        help_text=_("Activate this flag for these workspaces."),
    )

    def get_flush_keys(self, flush_keys=None):
        flush_keys = super().get_flush_keys(flush_keys)
        workspaces_cache_key = get_setting(Flag.FLAG_WORKSPACES_CACHE_KEY, Flag.FLAG_WORKSPACES_CACHE_KEY_DEFAULT)
        flush_keys.append(keyfmt(workspaces_cache_key, self.name))
        return flush_keys

    def is_active(self, request, read_only=False):
        is_active = super().is_active(request, read_only)
        if is_active:
            return is_active

        if not self.pk:
            return False

        workspace = getattr(request, "workspace", None)
        if workspace:
            workspace_ids = self._get_workspace_ids()
            return workspace.pk in workspace_ids

    def _get_workspace_ids(self):
        cache = get_cache()
        cache_key = keyfmt(
            get_setting(Flag.FLAG_WORKSPACES_CACHE_KEY, Flag.FLAG_WORKSPACES_CACHE_KEY_DEFAULT),
            self.name,
        )
        cached = cache.get(cache_key)
        if cached == CACHE_EMPTY:
            return set()
        if cached:
            return cached

        workspace_ids = set(self.workspaces.all().values_list("pk", flat=True))
        cache.add(cache_key, workspace_ids or CACHE_EMPTY)
        return workspace_ids
