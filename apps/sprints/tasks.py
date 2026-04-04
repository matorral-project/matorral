from apps.sprints.models import Sprint
from apps.workspaces.models import Workspace

from celery import shared_task


@shared_task
def create_next_sprints():
    """
    Auto-create next sprint for workspaces where:
    - There's an active or recent sprint
    - No planning sprint exists for the next period

    Runs daily via Celery beat.
    """
    for workspace in Workspace.objects.all().iterator(chunk_size=100):
        latest = Sprint.objects.for_workspace(workspace).latest_active_or_completed()

        if not latest:
            continue

        if not Sprint.objects.for_workspace(workspace).has_next_planning(latest.end_date):
            Sprint.objects.create_next_from(latest)
