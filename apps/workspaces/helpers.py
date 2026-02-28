from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from apps.issues.helpers import calculate_progress
from apps.issues.models import BaseIssue, Bug, Chore, IssueStatus, Story
from apps.projects.models import Project
from apps.sprints.models import Sprint
from apps.users.models import User

from allauth.account.models import EmailAddress

from .models import Invitation, Membership, Workspace
from .roles import ROLE_ADMIN
from .slugs import get_next_unique_workspace_slug
from .tasks import create_demo_project_task


def get_default_workspace_name_for_user(user: User) -> str:
    return (user.get_display_name().split("@")[0] or _("My Workspace")).title()


def get_default_workspace_for_user(user: User) -> Workspace | None:
    if user.workspaces.exists():
        return user.workspaces.first()
    return None


def create_default_workspace_for_user(user: User, workspace_name: str | None = None):
    workspace_name = workspace_name or get_default_workspace_name_for_user(user)
    slug = get_next_unique_workspace_slug(workspace_name)
    if not slug:
        slug = get_next_unique_workspace_slug(get_default_workspace_name_for_user(user))
    if not slug:
        slug = get_next_unique_workspace_slug("workspace")
    workspace = Workspace.objects.create(name=workspace_name, slug=slug)
    Membership.objects.create(workspace=workspace, user=user, role=ROLE_ADMIN)
    create_demo_project_task.delay(workspace.pk, user.pk)
    return workspace


def get_user_dashboard_data(user, workspace):
    active_sprint = Sprint.objects.for_workspace(workspace).active().first()

    if active_sprint:
        base_qs = (
            BaseIssue.objects.for_sprint(active_sprint)
            .work_items()
            .with_assignee(user)
            .select_related("project", "polymorphic_ctype")
        )
    else:
        base_qs = (
            BaseIssue.objects.for_workspace(workspace)
            .work_items()
            .with_assignee(user)
            .active()
            .select_related("project", "polymorphic_ctype")
        )

    in_progress = list(base_qs.with_status(IssueStatus.IN_PROGRESS))
    in_review = list(base_qs.with_status(IssueStatus.IN_REVIEW))
    blocked = list(base_qs.with_status(IssueStatus.BLOCKED))
    ready = [] if len(in_progress) > 1 else list(base_qs.with_status(IssueStatus.READY).ordered_by_priority()[:5])

    sprint_progress = None
    if active_sprint:
        work_items = []
        for model in [Story, Bug, Chore]:
            work_items.extend(model.objects.filter(sprint=active_sprint))
        sprint_progress = calculate_progress(work_items)

    return {
        "active_sprint": active_sprint,
        "sprint_progress": sprint_progress,
        "in_progress_issues": in_progress,
        "in_review_issues": in_review,
        "ready_issues": ready,
        "blocked_issues": blocked,
    }


def get_onboarding_status(user, workspace):
    if user.onboarding_completed:
        return {"should_show": False, "steps": [], "pending_count": 0}

    if workspace:
        demo_project = Project.objects.filter(workspace=workspace, created_by__isnull=True).first()
        demo_url = (
            demo_project.get_absolute_url()
            if demo_project
            else reverse("projects:project_list", kwargs={"workspace_slug": workspace.slug})
        )
        project_list_url = reverse("projects:project_list", kwargs={"workspace_slug": workspace.slug})
        members_url = reverse("workspaces:manage_workspace_members", kwargs={"workspace_slug": workspace.slug})
        sprint_list_url = reverse("sprints:sprint_list", kwargs={"workspace_slug": workspace.slug})
    else:
        demo_url = project_list_url = members_url = sprint_list_url = None

    steps = [
        {
            "key": "explore_demo",
            "title": _l("Explore the demo project"),
            "description": _l("See how projects and issues work with example data"),
            "icon": "fa-compass",
            "completed": user.onboarding_progress.get("demo_explored", False),
            "url": demo_url,
        },
        {
            "key": "create_project",
            "title": _l("Create your first project"),
            "description": _l("Set up a project to organize your team's work"),
            "icon": "fa-folder-plus",
            "completed": (
                Project.objects.filter(workspace=workspace, created_by=user).exists() if workspace else False
            ),
            "url": project_list_url,
        },
        {
            "key": "invite_teammates",
            "title": _l("Invite your teammates"),
            "description": _l("Collaborate by bringing your team onboard"),
            "icon": "fa-user-plus",
            "completed": (Invitation.objects.filter(workspace=workspace).exists() if workspace else False),
            "optional": True,
            "url": members_url,
        },
        {
            "key": "create_sprint",
            "title": _l("Create your first sprint"),
            "description": _l("Start planning work in time-boxed iterations"),
            "icon": "fa-bolt",
            "completed": (
                Sprint.objects.filter(workspace=workspace, created_by__isnull=False).exists() if workspace else False
            ),
            "optional": True,
            "url": sprint_list_url,
        },
    ]

    pending_count = sum(1 for step in steps if not step["completed"])
    completed_count = len(steps) - pending_count

    if pending_count == 0:
        user.onboarding_completed = True
        user.save(update_fields=["onboarding_completed"])
        return {"should_show": False, "steps": [], "pending_count": 0}

    return {
        "should_show": True,
        "steps": steps,
        "pending_count": pending_count,
        "completed_count": completed_count,
    }


def get_open_invitations_for_user(user: User) -> list[dict]:
    user_emails = list(EmailAddress.objects.filter(user=user).order_by("-primary"))
    if not user_emails:
        return []

    emails = {e.email for e in user_emails}
    open_invitations = (
        Invitation.objects.filter(email__in=list(emails), is_accepted=False)
        .exclude(workspace__membership__user=user)
        .values("id", "workspace__name", "email")
    )
    verified_emails = {email.email for email in user_emails if email.verified}
    return [
        {
            **inv,
            "workspace_name": inv["workspace__name"],
            "verified": inv["email"] in verified_emails,
        }
        for inv in open_invitations
    ]
