import logging
from collections import defaultdict
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.issues.models import (
    Bug,
    BugSeverity,
    Chore,
    Epic,
    IssuePriority,
    IssueStatus,
    Milestone,
    Story,
    Subtask,
    SubtaskStatus,
)
from apps.projects.models import Project, ProjectStatus
from apps.sprints.models import Sprint, SprintStatus
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)

# Demo data structure: milestones -> epics -> work items
MILESTONES = [
    {
        "title": "Private Alpha",
        "status": IssueStatus.DONE,
        "priority": IssuePriority.CRITICAL,
        "epics": [
            {
                "title": "User Authentication",
                "status": IssueStatus.DONE,
                "priority": IssuePriority.HIGH,
                "items": [
                    {
                        "title": "Email/password signup flow",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "OAuth social login (Google, GitHub)",
                        "type": "story",
                        "points": 8,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Password reset and email verification",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Session token not invalidated on logout",
                        "type": "bug",
                        "points": 2,
                        "severity": BugSeverity.MAJOR,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.CRITICAL,
                    },
                ],
            },
            {
                "title": "Team Management",
                "status": IssueStatus.DONE,
                "priority": IssuePriority.HIGH,
                "items": [
                    {
                        "title": "Create and configure teams",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Invite members via email",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Role-based access control (admin/member)",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Set up CI pipeline for team service",
                        "type": "chore",
                        "points": 2,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.LOW,
                    },
                ],
            },
            {
                "title": "Core API Foundation",
                "status": IssueStatus.DONE,
                "priority": IssuePriority.CRITICAL,
                "items": [
                    {
                        "title": "RESTful API with versioning",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Rate limiting and throttling",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "API key management for external access",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Intermittent 500 errors on concurrent requests",
                        "type": "bug",
                        "points": 3,
                        "severity": BugSeverity.CRITICAL,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.CRITICAL,
                    },
                ],
            },
        ],
    },
    {
        "title": "Private Beta",
        "status": IssueStatus.IN_PROGRESS,
        "priority": IssuePriority.HIGH,
        "epics": [
            {
                "title": "Billing and Subscriptions",
                "status": IssueStatus.IN_PROGRESS,
                "priority": IssuePriority.CRITICAL,
                "items": [
                    {
                        "title": "Stripe integration for payments",
                        "type": "story",
                        "points": 8,
                        "status": IssueStatus.DONE,
                        "priority": IssuePriority.CRITICAL,
                    },
                    {
                        "title": "Subscription plan management (free/pro/enterprise)",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.IN_PROGRESS,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Invoice generation and history",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.READY,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Usage-based billing metering",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.READY,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Proration not calculated on mid-cycle upgrade",
                        "type": "bug",
                        "points": 3,
                        "severity": BugSeverity.MAJOR,
                        "status": IssueStatus.READY,
                        "priority": IssuePriority.HIGH,
                    },
                ],
            },
            {
                "title": "Dashboard and Analytics",
                "status": IssueStatus.PLANNING,
                "priority": IssuePriority.MEDIUM,
                "items": [
                    {
                        "title": "Real-time metrics dashboard",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.PLANNING,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Custom report builder",
                        "type": "story",
                        "points": 8,
                        "status": IssueStatus.PLANNING,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Export data to CSV and PDF",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Write database migration for analytics tables",
                        "type": "chore",
                        "points": 2,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                ],
            },
            {
                "title": "Notification System",
                "status": IssueStatus.PLANNING,
                "priority": IssuePriority.MEDIUM,
                "items": [
                    {
                        "title": "In-app notification center",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.PLANNING,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Email digest preferences",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.PLANNING,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Webhook support for external integrations",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Slack and Microsoft Teams notifications",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                ],
            },
        ],
    },
    {
        "title": "Public Beta",
        "status": IssueStatus.PLANNING,
        "priority": IssuePriority.MEDIUM,
        "epics": [
            {
                "title": "Third-Party Integrations",
                "status": IssueStatus.DRAFT,
                "priority": IssuePriority.MEDIUM,
                "items": [
                    {
                        "title": "Zapier integration",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Salesforce CRM connector",
                        "type": "story",
                        "points": 8,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "OAuth provider for third-party apps",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.HIGH,
                    },
                ],
            },
            {
                "title": "Performance and Scalability",
                "status": IssueStatus.DRAFT,
                "priority": IssuePriority.HIGH,
                "items": [
                    {
                        "title": "Database query optimization audit",
                        "type": "chore",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "CDN setup for static assets",
                        "type": "chore",
                        "points": 2,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                    {
                        "title": "Horizontal scaling with load balancer",
                        "type": "story",
                        "points": 8,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Memory leak in background job processor",
                        "type": "bug",
                        "points": 5,
                        "severity": BugSeverity.MAJOR,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.CRITICAL,
                    },
                ],
            },
            {
                "title": "Public Website and Onboarding",
                "status": IssueStatus.DRAFT,
                "priority": IssuePriority.MEDIUM,
                "items": [
                    {
                        "title": "Marketing landing page",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Interactive product tour",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Self-service onboarding wizard",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                ],
            },
        ],
    },
    {
        "title": "Public Launch",
        "status": IssueStatus.DRAFT,
        "priority": IssuePriority.MEDIUM,
        "epics": [
            {
                "title": "Security and Compliance",
                "status": IssueStatus.DRAFT,
                "priority": IssuePriority.CRITICAL,
                "items": [
                    {
                        "title": "SOC 2 Type II compliance audit",
                        "type": "chore",
                        "points": 8,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.CRITICAL,
                    },
                    {
                        "title": "Penetration testing and vulnerability scan",
                        "type": "chore",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "GDPR data export and deletion",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Two-factor authentication (TOTP)",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                ],
            },
            {
                "title": "Launch Readiness",
                "status": IssueStatus.DRAFT,
                "priority": IssuePriority.HIGH,
                "items": [
                    {
                        "title": "Production environment setup and hardening",
                        "type": "chore",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.HIGH,
                    },
                    {
                        "title": "Disaster recovery and backup strategy",
                        "type": "chore",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Public API documentation site",
                        "type": "story",
                        "points": 5,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.MEDIUM,
                    },
                    {
                        "title": "Customer support helpdesk integration",
                        "type": "story",
                        "points": 3,
                        "status": IssueStatus.DRAFT,
                        "priority": IssuePriority.LOW,
                    },
                ],
            },
        ],
    },
]

# Sprint assignments: maps sprint type to (item titles, target statuses)
SPRINT_COMPLETED_ITEMS = [
    "Email/password signup flow",
    "OAuth social login (Google, GitHub)",
    "Password reset and email verification",
    "Session token not invalidated on logout",
    "Create and configure teams",
]

SPRINT_ACTIVE_ITEMS = {
    "Stripe integration for payments": IssueStatus.DONE,
    "Subscription plan management (free/pro/enterprise)": IssueStatus.IN_PROGRESS,
    "Invoice generation and history": IssueStatus.READY,
    "Usage-based billing metering": IssueStatus.READY,
    "Proration not calculated on mid-cycle upgrade": IssueStatus.READY,
}

SPRINT_PLANNING_ITEMS = [
    "In-app notification center",
    "Email digest preferences",
]

# Subtasks for key work items
SUBTASKS = {
    "Stripe integration for payments": [
        ("Set up Stripe API keys and webhook endpoint", SubtaskStatus.DONE),
        ("Implement payment intent creation flow", SubtaskStatus.DONE),
        ("Handle webhook events (payment succeeded/failed)", SubtaskStatus.DONE),
        ("Add idempotency keys for retry safety", SubtaskStatus.DONE),
    ],
    "Real-time metrics dashboard": [
        ("Design dashboard wireframes", SubtaskStatus.TODO),
        ("Implement WebSocket connection for live updates", SubtaskStatus.TODO),
        ("Build chart components (line, bar, pie)", SubtaskStatus.TODO),
    ],
    "SOC 2 Type II compliance audit": [
        ("Document access control policies", SubtaskStatus.TODO),
        ("Set up audit logging for all sensitive operations", SubtaskStatus.TODO),
        ("Engage external auditor and schedule review", SubtaskStatus.TODO),
    ],
}


def _create_milestones(project, user):
    """Create milestones via bulk_create with pre-generated keys."""
    milestones = []
    for i, m_data in enumerate(MILESTONES, start=1):
        milestones.append(
            Milestone(
                project=project,
                key=f"M-{i}",
                title=m_data["title"],
                status=m_data["status"],
                priority=m_data["priority"],
                owner=user,
            )
        )
    created = Milestone.objects.bulk_create(milestones)
    return {m.title: m for m in created}


def _create_epics_and_items(project, user, milestones_by_title):
    """Create epics (add_root) and work items (add_child) sequentially due to treebeard."""
    work_items_by_title = {}
    item_type_map = {"story": Story, "bug": Bug, "chore": Chore}

    for m_data in MILESTONES:
        milestone = milestones_by_title[m_data["title"]]
        for epic_data in m_data["epics"]:
            epic = Epic.add_root(
                project=project,
                title=epic_data["title"],
                status=epic_data["status"],
                priority=epic_data.get("priority", IssuePriority.MEDIUM),
                milestone=milestone,
                assignee=user,
            )

            for item_data in epic_data["items"]:
                item_cls = item_type_map[item_data["type"]]
                kwargs = {
                    "project": project,
                    "title": item_data["title"],
                    "status": item_data["status"],
                    "priority": item_data.get("priority", IssuePriority.MEDIUM),
                    "estimated_points": item_data["points"],
                    "assignee": user,
                }
                if item_data["type"] == "bug":
                    kwargs["severity"] = item_data.get("severity", BugSeverity.MINOR)

                child = epic.add_child(instance=item_cls(**kwargs))
                work_items_by_title[child.title] = child

    return work_items_by_title


def _create_sprints(workspace, user, today):
    """Create 3 sprints via bulk_create with pre-generated keys."""
    four_weeks_ago = today - timedelta(weeks=4)
    two_weeks_ago = today - timedelta(weeks=2)
    # Next Monday for the planning sprint
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    sprints = Sprint.objects.bulk_create(
        [
            Sprint(
                workspace=workspace,
                key="SPRINT-1",
                name="Sprint #1",
                goal="Complete core authentication and team management features.",
                status=SprintStatus.COMPLETED,
                start_date=four_weeks_ago,
                end_date=two_weeks_ago,
                owner=user,
            ),
            Sprint(
                workspace=workspace,
                key="SPRINT-2",
                name="Sprint #2",
                goal="Implement billing integration and subscription management.",
                status=SprintStatus.ACTIVE,
                start_date=two_weeks_ago,
                end_date=today,
                owner=user,
            ),
            Sprint(
                workspace=workspace,
                key="SPRINT-3",
                name="Sprint #3",
                goal="Build notification system foundation.",
                status=SprintStatus.PLANNING,
                start_date=next_monday,
                end_date=next_monday + timedelta(weeks=2),
                owner=user,
            ),
        ]
    )
    return {s.status: s for s in sprints}


def _bulk_update_sprint(items, sprint, status=None):
    """Update sprint (and optionally status) on work items, grouped by concrete model."""
    by_model = defaultdict(list)
    for item in items:
        by_model[type(item)].append(item.pk)

    for model_cls, pks in by_model.items():
        update_kwargs = {"sprint": sprint}
        if status is not None:
            update_kwargs["status"] = status
        model_cls.objects.filter(pk__in=pks).update(**update_kwargs)


def _assign_sprint_items(work_items_by_title, sprints):
    """Assign work items to sprints via bulk updates."""
    # Completed sprint: all items DONE
    completed_sprint = sprints[SprintStatus.COMPLETED]
    completed_items = [work_items_by_title[title] for title in SPRINT_COMPLETED_ITEMS]
    _bulk_update_sprint(completed_items, completed_sprint, status=IssueStatus.DONE)

    # Active sprint: assign sprint first, then set individual statuses
    active_sprint = sprints[SprintStatus.ACTIVE]
    active_items = [work_items_by_title[title] for title in SPRINT_ACTIVE_ITEMS]
    _bulk_update_sprint(active_items, active_sprint)
    for title, status in SPRINT_ACTIVE_ITEMS.items():
        item = work_items_by_title[title]
        type(item).objects.filter(pk=item.pk).update(status=status)

    # Planning sprint
    planning_sprint = sprints[SprintStatus.PLANNING]
    planning_items = [work_items_by_title[title] for title in SPRINT_PLANNING_ITEMS]
    _bulk_update_sprint(planning_items, planning_sprint, status=IssueStatus.PLANNING)


def _create_subtasks(work_items_by_title):
    """Create subtasks via bulk_create."""
    story_ct = ContentType.objects.get_for_model(Story)
    chore_ct = ContentType.objects.get_for_model(Chore)

    subtasks = []
    for item_title, task_list in SUBTASKS.items():
        item = work_items_by_title[item_title]
        ct = chore_ct if isinstance(item, Chore) else story_ct
        for position, (title, status) in enumerate(task_list):
            subtasks.append(
                Subtask(
                    content_type=ct,
                    object_id=item.pk,
                    title=title,
                    status=status,
                    position=position,
                )
            )
    Subtask.objects.bulk_create(subtasks)


@transaction.atomic
def create_demo_project(workspace: Workspace, user) -> Project:
    """
    Create a full demo project with milestones, epics, work items, sprints, and subtasks.

    This populates a new workspace so users see a realistic example of how the tool works.
    """
    today = timezone.now().date()

    # 1. Create project
    project = Project.objects.create(
        workspace=workspace,
        name="Acme SaaS Platform",
        description="A modern SaaS platform with billing, analytics, and integrations.",
        status=ProjectStatus.ACTIVE,
        lead=user,
    )

    # 2. Create milestones (bulk)
    milestones_by_title = _create_milestones(project, user)

    # 3. Create epics and work items (sequential due to treebeard)
    work_items_by_title = _create_epics_and_items(project, user, milestones_by_title)

    # 4. Create sprints (bulk)
    sprints = _create_sprints(workspace, user, today)

    # 5. Assign items to sprints (bulk updates)
    _assign_sprint_items(work_items_by_title, sprints)

    # 6. Update sprint velocity
    for sprint in sprints.values():
        sprint.update_velocity()

    # 7. Create subtasks (bulk)
    _create_subtasks(work_items_by_title)

    logger.info("Created demo project '%s' in workspace '%s'", project.name, workspace.name)
    return project
