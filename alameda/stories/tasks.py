from alameda.taskapp.celery import app

from .models import Epic, EpicState, Story, StoryState


@app.task(ignore_result=True)
def duplicate_stories(story_ids):
    for pk in story_ids:
        try:
            story = Story.objects.get(pk=pk)
        except Story.DoesNotExist:
            continue

        story.duplicate()


@app.task(ignore_result=True)
def remove_stories(story_ids):
    Story.objects.filter(id__in=story_ids).delete()


@app.task(ignore_result=True)
def story_set_assignee(story_ids, user_id):
    Story.objects.filter(id__in=story_ids).update(assignee=user_id)


@app.task(ignore_result=True)
def story_set_state(story_ids, state_slug):
    try:
        state = StoryState.objects.get(slug=state_slug)
    except StoryState.DoesNotExist:
        return

    Story.objects.filter(id__in=story_ids).update(state=state)


@app.task(ignore_result=True)
def duplicate_epics(epic_ids):
    for pk in epic_ids:
        try:
            epic = Epic.objects.get(pk=pk)
        except Epic.DoesNotExist:
            continue

        epic.duplicate()


@app.task(ignore_result=True)
def remove_epics(epic_ids):
    Epic.objects.filter(id__in=epic_ids).delete()


@app.task(ignore_result=True)
def epic_set_owner(epic_ids, user_id):
    Epic.objects.filter(id__in=epic_ids).update(owner=user_id)


@app.task(ignore_result=True)
def epic_set_state(epic_ids, state_slug):
    try:
        state = EpicState.objects.get(slug=state_slug)
    except EpicState.DoesNotExist:
        return

    Epic.objects.filter(id__in=epic_ids).update(state=state)


@app.task(ignore_result=True)
def reset_epic(story_ids):
    Story.objects.filter(id__in=story_ids).update(epic=None)
