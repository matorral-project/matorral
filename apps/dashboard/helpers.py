from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.issues.helpers import calculate_progress
from apps.issues.models import BaseIssue, Bug, Chore, IssueStatus, Story
from apps.projects.models import Project
from apps.sprints.models import Sprint
from apps.workspaces.models import Invitation


def get_user_dashboard_data(user, workspace):
    """
    Get dashboard data for a user within a workspace.

    Returns a dict with:
    - active_sprint: The currently active sprint in the workspace, or None
    - sprint_progress: Progress dict for the active sprint, or None
    - in_progress_issues: Issues assigned to the user with IN_PROGRESS status
    - in_review_issues: Issues assigned to the user with IN_REVIEW status
    - ready_issues: Issues assigned to the user with READY status (only if 1 or fewer in-progress)
    - blocked_issues: Issues assigned to the user with BLOCKED status
    """
    active_sprint = Sprint.objects.for_workspace(workspace).active().first()

    if active_sprint:
        # When there's an active sprint, show work items from that sprint
        base_qs = (
            BaseIssue.objects.for_sprint(active_sprint)
            .work_items()
            .with_assignee(user)
            .select_related("project", "polymorphic_ctype")
        )
    else:
        # Without an active sprint, show all active work items in the workspace
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

    # Show ready issues if there are one or fewer in-progress issues
    ready = [] if len(in_progress) > 1 else list(base_qs.with_status(IssueStatus.READY).ordered_by_priority()[:5])

    # Calculate sprint progress
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
    """
    Calculate onboarding progress for a user within a workspace.

    Returns dict with:
    - should_show: Boolean indicating if onboarding should be displayed
    - steps: List of step dicts with {key, title, description, completed, url, icon}
    - pending_count: Number of incomplete steps
    """
    if user.onboarding_completed:
        return {
            "should_show": False,
            "steps": [],
            "pending_count": 0,
        }

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
            "title": _("Explore the demo project"),
            "description": _("See how projects and issues work with example data"),
            "icon": "fa-compass",
            "completed": user.onboarding_progress.get("demo_explored", False),
            "url": demo_url,
        },
        {
            "key": "create_project",
            "title": _("Create your first project"),
            "description": _("Set up a project to organize your team's work"),
            "icon": "fa-folder-plus",
            "completed": (
                Project.objects.filter(workspace=workspace, created_by=user).exists() if workspace else False
            ),
            "url": project_list_url,
        },
        {
            "key": "invite_teammates",
            "title": _("Invite your teammates"),
            "description": _("Collaborate by bringing your team onboard"),
            "icon": "fa-user-plus",
            "completed": (Invitation.objects.filter(workspace=workspace).exists() if workspace else False),
            "optional": True,
            "url": members_url,
        },
        {
            "key": "create_sprint",
            "title": _("Create your first sprint"),
            "description": _("Start planning work in time-boxed iterations"),
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

    # Auto-complete onboarding when all steps are done
    if pending_count == 0:
        user.onboarding_completed = True
        user.save(update_fields=["onboarding_completed"])
        return {
            "should_show": False,
            "steps": [],
            "pending_count": 0,
        }

    return {
        "should_show": True,
        "steps": steps,
        "pending_count": pending_count,
        "completed_count": completed_count,
    }
