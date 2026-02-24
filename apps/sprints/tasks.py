from datetime import timedelta

from apps.sprints.models import Sprint, SprintStatus
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
        # Find the latest sprint (active or most recent completed)
        latest = (
            Sprint.objects.for_workspace(workspace)
            .filter(status__in=[SprintStatus.ACTIVE, SprintStatus.COMPLETED])
            .order_by("-end_date")
            .first()
        )

        if not latest:
            continue

        # Check if next sprint already exists
        next_exists = (
            Sprint.objects.for_workspace(workspace)
            .filter(start_date__gt=latest.end_date, status=SprintStatus.PLANNING)
            .exists()
        )

        if not next_exists:
            # Create next sprint starting day after current ends
            duration = latest.end_date - latest.start_date
            sprint = Sprint.objects.create(
                workspace=workspace,
                name="",  # Will be set after key is generated
                start_date=latest.end_date + timedelta(days=1),
                end_date=latest.end_date + timedelta(days=1) + duration,
                status=SprintStatus.PLANNING,
                capacity=latest.capacity,  # Copy capacity from previous
            )
            # Extract sprint number from auto-generated key and create friendly name
            sprint_number = sprint.key.split("-")[-1]
            sprint.name = f"Sprint #{sprint_number}"
            sprint.save(update_fields=["name"])
