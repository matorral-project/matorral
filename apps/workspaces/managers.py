from django.db import models

from allauth.account.models import EmailAddress


class WorkspaceQuerySet(models.QuerySet):
    def for_user(self, user):
        """Return workspaces the given user is a member of."""
        return self.filter(members=user)


class InvitationQuerySet(models.QuerySet):
    def pending_for_user(self, user):
        """Return open invitations matching any of the user's email addresses."""

        emails = list(EmailAddress.objects.filter(user=user).values_list("email", flat=True))
        if not emails:
            return self.none()

        return self.filter(email__in=emails, is_accepted=False).exclude(workspace__membership__user=user)
