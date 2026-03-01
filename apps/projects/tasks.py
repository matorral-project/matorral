from apps.projects.models import Project
from apps.workspaces.models import Workspace

from celery import shared_task


@shared_task
def move_project_task(project_id, target_workspace_id):
    """Move a project to a different workspace asynchronously."""
    project = Project.objects.get(pk=project_id)
    workspace = Workspace.objects.get(pk=target_workspace_id)
    project.move(workspace)
