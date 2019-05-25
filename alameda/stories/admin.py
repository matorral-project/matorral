from django import forms
from django.contrib import admin
from django.utils import timezone

from django_admin_listfilter_dropdown.filters import ChoiceDropdownFilter, RelatedDropdownFilter

from simple_history.admin import SimpleHistoryAdmin

from alameda.sprints.models import Sprint

from .models import Epic, EpicState, Story, StoryState, Task


class EpicForm(forms.ModelForm):

    class Meta:
        model = Epic
        exclude = ['created_at', 'updated_at', 'completed_at', 'total_points',
                   'story_count', 'progress', 'points_done']


class StoryForm(forms.ModelForm):

    class Meta:
        model = Story
        exclude = ['created_at', 'updated_at', 'completed_at']


class EpicAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'priority', 'progress', 'story_count', 'total_points',
                    'points_done', 'state', 'owner', 'created_at', 'completed_at')
    list_filter = [
        ('priority', ChoiceDropdownFilter),
        ('state', RelatedDropdownFilter),
        ('owner', RelatedDropdownFilter)
    ]
    search_fields = ['title']
    form = EpicForm
    actions = ['mark_as_done']

    def mark_as_done(self, request, queryset):
        count = queryset.update(completed_at=timezone.now(), state='dn')
        self.message_user(request, f"{count} epics successfully maked as done")


class StoryAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'epic', 'priority', 'state', 'points', 'assignee', 'created_at', 'completed_at')
    list_filter = ('epic', 'sprint', 'state', 'priority', 'assignee')
    list_filter = [
        ('state', RelatedDropdownFilter),
        ('epic', RelatedDropdownFilter),
        ('sprint', RelatedDropdownFilter),
        ('assignee', RelatedDropdownFilter)
    ]
    search_fields = ['title', 'epic__title', 'sprint__title', 'assignee__username']
    form = StoryForm
    actions = ['reset_sprint', 'finish_sprint', 'mark_as_done']

    def reset_sprint(self, request, queryset):
        # given a set of stories it sets the sprint field to None
        count = queryset.update(sprint=None)
        self.message_user(request, f"{count} stories successfully reseted")

    def finsh_sprint(self, request, queryset):
        # given a set of stories it sets the sprint field to point to the next
        # sprint instance
        try:
            next_sprint = Sprint.objects.get(completed_at__isnull=True)
        except Sprint.DoesNotExist:
            self.message_user(request, f"There's no current sprint. Please create one first.")
        else:
            count = queryset.update(sprint=next_sprint)
            self.message_user(request, f"{count} stories moved to the next sprint")

    def mark_as_done(self, request, queryset):
        count = queryset.update(completed_at=timezone.now(), state='dn')
        self.message_user(request, f"{count} stories successfully maked as done")


class TaskAdmin(admin.ModelAdmin):
    actions_on_bottom = True
    list_display = ('title', 'created_at', 'completed_at')
    search_fields = ['title']
    actions = ['mark_as_done']

    def mark_as_done(self, request, queryset):
        count = queryset.update(completed_at=timezone.now())
        self.message_user(request, f"{count} tasks successfully maked as done")


admin.site.register(Epic, EpicAdmin)
admin.site.register(EpicState)
admin.site.register(Story, StoryAdmin)
admin.site.register(StoryState)
admin.site.register(Task, TaskAdmin)
