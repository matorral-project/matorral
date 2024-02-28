from matorral.taskapp.celery import app

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

    for epic in Epic.objects.filter(story__id__in=story_ids).distinct():
        epic.update_state()
        epic.update_points_and_progress()

    from matorral.sprints.models import Sprint

    for sprint in Sprint.objects.filter(story__id__in=story_ids).distinct():
        sprint.update_points_and_progress()


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

    for epic in Epic.objects.filter(id__in=epic_ids):
        epic.update_state()


@app.task(ignore_result=True)
def reset_epic(story_ids):
    # get affected sprint and epic ids before removing them: evaluate queryset
    # because they're lazy :)
    epic_ids = list(Story.objects.filter(id__in=story_ids).values_list("epic_id", flat=True))
    sprint_ids = list(Story.objects.filter(id__in=story_ids).values_list("sprint_id", flat=True))

    Story.objects.filter(id__in=story_ids).update(epic=None)

    for epic in Epic.objects.filter(id__in=epic_ids):
        epic.update_state()
        epic.update_points_and_progress()

    from matorral.sprints.models import Sprint

    for sprint in Sprint.objects.filter(id__in=sprint_ids):
        sprint.update_points_and_progress()


@app.task(ignore_result=True)
def handle_story_change(story_id):
    try:
        story = Story.objects.get(pk=story_id)
    except Story.DoesNotExist:
        return

    if story.epic is not None:
        story.epic.update_points_and_progress()
        story.epic.update_state()

    if story.sprint is not None:
        story.sprint.update_points_and_progress()


@app.task(ignore_result=True)
def handle_epic_change(epic_id):
    try:
        epic = Epic.objects.get(pk=epic_id)
    except Epic.DoesNotExist:
        return

    epic.update_points_and_progress()


@app.task(ignore_result=True)
def story_set_epic(story_ids, epic_id):
    try:
        epic = Epic.objects.get(pk=epic_id)
    except Epic.DoesNotExist:
        return

    for story in Story.objects.filter(id__in=story_ids):
        story.epic = epic
        story.save()


@app.task(ignore_result=True)
def story_set_sprint(story_ids, sprint_id):
    from matorral.sprints.models import Sprint

    try:
        sprint = Sprint.objects.get(pk=sprint_id)
    except Sprint.DoesNotExist:
        return

    for story in Story.objects.filter(id__in=story_ids):
        story.sprint = sprint
        story.save()
