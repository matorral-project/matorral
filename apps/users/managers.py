from django.contrib.auth.models import UserManager as BaseUserManager
from django.db import models


class UserQuerySet(models.QuerySet):
    """Custom QuerySet for User model."""

    def for_workspace(self, workspace) -> UserQuerySet:
        """Filter users who are members of the given workspace."""
        return self.filter(workspace_memberships__workspace=workspace)

    def for_choices(self) -> UserQuerySet:
        """
        Return only the fields needed for form choice fields and display.
        Use this when populating ModelChoiceField/ModelMultipleChoiceField querysets.
        Includes first_name/last_name for get_display_name() to avoid N+1 queries.
        """
        return self.only("id", "email", "first_name", "last_name")


class UserManager(BaseUserManager.from_queryset(UserQuerySet)):
    """Custom Manager for User model combining UserManager with UserQuerySet."""
