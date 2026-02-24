import logging

from django.apps import apps

from apps.workspaces.demo_data import create_demo_project

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def create_demo_project_task(workspace_id: int, user_id: int):
    """Create demo project data for a newly created workspace."""
    Workspace = apps.get_model("workspaces", "Workspace")
    CustomUser = apps.get_model("users", "CustomUser")

    try:
        workspace = Workspace.objects.get(pk=workspace_id)
        user = CustomUser.objects.get(pk=user_id)
    except (Workspace.DoesNotExist, CustomUser.DoesNotExist):
        logger.warning(
            "Workspace %s or user %s not found for demo project creation",
            workspace_id,
            user_id,
        )
        return

    create_demo_project(workspace, user)


DEMO_USER_EMAIL = "demo@example.com"
DEMO_USER_PASSWORD = "demouser789"


@shared_task
def reset_demo_workspace_data():
    """Delete all projects, sprints, and related data for the demo user's workspace.

    Runs daily to keep the demo environment fresh for new visitors.
    DB cascades handle deletion of milestones, epics, stories, bugs, chores, issues, and subtasks.
    """
    CustomUser = apps.get_model("users", "CustomUser")
    Workspace = apps.get_model("workspaces", "Workspace")
    Project = apps.get_model("projects", "Project")
    Sprint = apps.get_model("sprints", "Sprint")

    try:
        user = CustomUser.objects.get(email=DEMO_USER_EMAIL)
    except CustomUser.DoesNotExist:
        logger.warning("Demo user '%s' not found, skipping workspace reset", DEMO_USER_EMAIL)
        return

    user.set_password(DEMO_USER_PASSWORD)
    user.save(update_fields=["password"])
    logger.info("Reset demo user password for '%s'", DEMO_USER_EMAIL)

    workspaces = Workspace.objects.for_user(user)

    if not workspaces.exists():
        logger.warning("No workspaces found for demo user '%s', skipping reset", DEMO_USER_EMAIL)
        return

    for workspace in workspaces.iterator():
        sprint_count, _ = Sprint.objects.filter(workspace=workspace).delete()
        project_count, _ = Project.objects.filter(workspace=workspace).delete()
        logger.info(
            "Reset demo workspace '%s': deleted %d sprints, %d projects (and cascaded children)",
            workspace.slug,
            sprint_count,
            project_count,
        )
