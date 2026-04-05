from apps.sprints.models import Sprint

from celery import shared_task


@shared_task
def create_next_sprints():
    """
    Auto-create next sprint for workspaces where:
    - There's an active or recent sprint
    - No planning sprint exists for the next period

    Runs daily via Celery beat.
    """
    for sprint in Sprint.objects.needing_next_sprint().iterator(chunk_size=100):
        Sprint.objects.create_next_from(sprint)
