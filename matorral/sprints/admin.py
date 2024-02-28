from django.contrib import admin

from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter

from simple_history.admin import SimpleHistoryAdmin

from .models import Sprint


class SprintAdmin(SimpleHistoryAdmin):
    actions_on_bottom = True
    list_display = ("title", "starts_at", "ends_at", "state", "workspace")
    search_fields = ["title"]
    list_filter = [("workspace", RelatedDropdownFilter)]


admin.site.register(Sprint, SprintAdmin)
