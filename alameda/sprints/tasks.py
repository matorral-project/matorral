from datetime import date

from alameda.taskapp.celery import app

from alameda.sprints.models import Sprint


@app.task(ignore_result=True)
def update_state():
    # move to state=started all sprints that have began
    Sprint.objects.filter(state=Sprint.STATE_UNSTARTED, starts_at__gte=date.today()).update(state=Sprint.STATE_STARTED)
    # move to state=done all sprints that have finished
    Sprint.objects.filter(state=Sprint.STATE_STARTED, ends_at__gte=date.today()).update(state=Sprint.STATE_DONE)
