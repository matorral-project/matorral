from django.contrib import admin

from simple_history.admin import SimpleHistoryAdmin

from .models import Sprint


class SprintAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ('title', 'starts_at', 'ends_at', 'state')
    search_fields = ['title']


admin.site.register(Sprint, SprintAdmin)
