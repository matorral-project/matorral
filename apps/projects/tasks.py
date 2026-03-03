import uuid

from django.core.cache import cache

from apps.projects.models import Project
from apps.workspaces.models import Workspace

from celery import shared_task

MOVE_PROGRESS_TIMEOUT = 300  # 5 minutes


def start_move_operation(project_ids, target_workspace_id):
    """Create a move operation with progress tracking and dispatch the Celery task.

    Returns the operation_id used to poll progress.
    """
    operation_id = uuid.uuid4().hex
    cache.set(
        f"move_projects_{operation_id}",
        {"total": len(project_ids), "completed": 0, "status": "in_progress"},
        timeout=MOVE_PROGRESS_TIMEOUT,
    )
    move_projects_task.delay(project_ids, target_workspace_id, operation_id)
    return operation_id


@shared_task
def move_projects_task(project_ids, target_workspace_id, operation_id=None):
    """Move one or more projects to a different workspace."""
    workspace = Workspace.objects.get(pk=target_workspace_id)
    total = len(project_ids)

    for i, project_id in enumerate(project_ids):
        project = Project.objects.get(pk=project_id)
        project.move(workspace)

        if operation_id:
            completed = i + 1
            status = "completed" if completed == total else "in_progress"
            cache.set(
                f"move_projects_{operation_id}",
                {"total": total, "completed": completed, "status": status},
                timeout=MOVE_PROGRESS_TIMEOUT,
            )
