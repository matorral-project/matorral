from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.issues.models import BaseIssue

from .models import Invitation


class LimitExceededError(Exception):
    """Raised when a free-tier usage limit is exceeded."""

    def __init__(self, message, limit_name):
        self.limit_name = limit_name
        super().__init__(message)


def _get_limit(name):
    return settings.FREE_TIER_LIMITS[name]


def get_member_count(workspace):
    return workspace.members.count()


def get_weekly_invitation_count(workspace):
    one_week_ago = timezone.now() - timedelta(days=7)
    return Invitation.objects.filter(workspace=workspace, created_at__gte=one_week_ago).count()


def get_work_item_count(workspace):
    return BaseIssue.objects.filter(project__workspace=workspace).count()


def can_add_member(workspace):
    return get_member_count(workspace) < _get_limit("MAX_MEMBERS_PER_WORKSPACE")


def can_send_invitation(workspace):
    return get_weekly_invitation_count(workspace) < _get_limit("MAX_INVITATIONS_PER_WEEK")


def can_create_work_item(workspace):
    return get_work_item_count(workspace) < _get_limit("MAX_WORK_ITEMS_PER_WORKSPACE")


def check_member_limit(workspace):
    """Raise LimitExceededError if workspace is at member capacity."""
    limit = _get_limit("MAX_MEMBERS_PER_WORKSPACE")
    if get_member_count(workspace) >= limit:
        raise LimitExceededError(
            _("This workspace has reached its limit of %(limit)d members.") % {"limit": limit},
            limit_name="MAX_MEMBERS_PER_WORKSPACE",
        )


def check_invitation_limit(workspace):
    """Raise LimitExceededError if workspace has sent too many invitations this week."""
    limit = _get_limit("MAX_INVITATIONS_PER_WEEK")
    if get_weekly_invitation_count(workspace) >= limit:
        raise LimitExceededError(
            _("This workspace has reached its limit of %(limit)d invitations per week.") % {"limit": limit},
            limit_name="MAX_INVITATIONS_PER_WEEK",
        )


def check_work_item_limit(workspace):
    """Raise LimitExceededError if workspace has reached the work item limit."""
    limit = _get_limit("MAX_WORK_ITEMS_PER_WORKSPACE")
    if get_work_item_count(workspace) >= limit:
        raise LimitExceededError(
            _("This workspace has reached its limit of %(limit)d work items.") % {"limit": limit},
            limit_name="MAX_WORK_ITEMS_PER_WORKSPACE",
        )


def get_limits_context(workspace):
    """Return current counts and limits for template display."""
    return {
        "member_count": get_member_count(workspace),
        "member_limit": _get_limit("MAX_MEMBERS_PER_WORKSPACE"),
        "weekly_invitation_count": get_weekly_invitation_count(workspace),
        "weekly_invitation_limit": _get_limit("MAX_INVITATIONS_PER_WEEK"),
        "work_item_count": get_work_item_count(workspace),
        "work_item_limit": _get_limit("MAX_WORK_ITEMS_PER_WORKSPACE"),
    }
