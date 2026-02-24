from django.db import models


class WorkspaceQuerySet(models.QuerySet):
    def for_user(self, user):
        """Return workspaces the given user is a member of."""
        return self.filter(members=user)
