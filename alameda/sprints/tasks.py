from datetime import date

from alameda.taskapp.celery import app

from alameda.sprints.models import Sprint


@app.task(ignore_result=True)
def update_state():
    # move to state=started all sprints that have began
    Sprint.objects.filter(state=Sprint.STATE_UNSTARTED, ends_at__gte=date.today()).update(state=Sprint.STATE_STARTED)
    # move to state=done all sprints that have finished
    Sprint.objects.exclude(state=Sprint.STATE_DONE).filter(ends_at__lt=date.today()).update(state=Sprint.STATE_DONE)
