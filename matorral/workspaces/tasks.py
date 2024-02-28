from matorral.taskapp.celery import app

from matorral.workspaces.models import Workspace


@app.task(ignore_result=True)
def duplicate_workspaces(workspace_ids):
    for pk in workspace_ids:
        try:
            workspace = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            continue

        workspace.duplicate()


@app.task(ignore_result=True)
def remove_workspaces(workspace_ids):
    Workspace.objects.filter(id__in=workspace_ids).delete()
