from datetime import date

from matorral.taskapp.celery import app

from matorral.sprints.models import Sprint


@app.task(ignore_result=True)
def update_state():
    # move to state=started all sprints that have began
    Sprint.objects.filter(state=Sprint.STATE_UNSTARTED, ends_at__gte=date.today()).update(state=Sprint.STATE_STARTED)
    # move to state=done all sprints that have finished
    Sprint.objects.exclude(state=Sprint.STATE_DONE).filter(ends_at__lt=date.today()).update(state=Sprint.STATE_DONE)


@app.task(ignore_result=True)
def duplicate_sprints(sprint_ids):
    for pk in sprint_ids:
        try:
            sprint = Sprint.objects.get(pk=pk)
        except Sprint.DoesNotExist:
            continue

        sprint.duplicate()


@app.task(ignore_result=True)
def remove_sprints(sprint_ids):
    Sprint.objects.filter(id__in=sprint_ids).delete()


@app.task(ignore_result=True)
def reset_sprint(story_ids):
    from matorral.stories.models import Story

    # get affected sprint ids before removing them: evaluate queryset because
    # they're lazy :)
    sprint_ids = list(Story.objects.filter(id__in=story_ids).values_list('sprint_id', flat=True))

    Story.objects.filter(id__in=story_ids).update(sprint=None)

    for sprint in Sprint.objects.filter(id__in=sprint_ids):
        sprint.update_points_and_progress()


@app.task(ignore_result=True)
def handle_sprint_change(epic_id):
    try:
        sprint = Sprint.objects.get(pk=epic_id)
    except Sprint.DoesNotExist:
        return

    sprint.update_points_and_progress()
