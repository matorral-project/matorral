from django import forms
from django.contrib import admin

from simple_history.admin import SimpleHistoryAdmin

from .models import Epic, EpicState, Sprint, Story, StoryState, Task


class EpicForm(forms.ModelForm):

    class Meta:
        model = Epic
        exclude = ['created_at', 'updated_at', 'completed_at']


class StoryForm(forms.ModelForm):

    class Meta:
        model = Story
        exclude = ['created_at', 'updated_at', 'completed_at']


class SprintAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'created_at', 'completed_at')
    search_fields = ['title']


class EpicAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'priority', 'state', 'owner', 'created_at', 'completed_at')
    list_filter = ('priority', 'state', 'owner')
    list_select_related = ('state', 'owner')
    search_fields = ['title']
    form = EpicForm


class StoryAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'epic', 'priority', 'state', 'points', 'assignee', 'created_at', 'completed_at')
    list_filter = ('epic', 'sprint', 'state', 'priority', 'assignee')
    list_select_related = ('epic', 'state', 'assignee')
    search_fields = ['title', 'epic__title', 'sprint__title', 'assignee__username']
    form = StoryForm


class TaskAdmin(admin.ModelAdmin):
    actions_on_bottom = True
    list_display = ('title', 'created_at', 'completed_at')
    search_fields = ['title']


admin.site.register(Epic, EpicAdmin)
admin.site.register(EpicState)
admin.site.register(Sprint, SprintAdmin)
admin.site.register(Story, StoryAdmin)
admin.site.register(StoryState)
admin.site.register(Task, TaskAdmin)
