from django.contrib import admin

from .models import Workspace


class WorkspaceAdmin(admin.ModelAdmin):
    actions_on_bottom = True
    list_display = ("name", "owner", "created_at", "updated_at")
    search_fields = ["name"]


admin.site.register(Workspace, WorkspaceAdmin)
