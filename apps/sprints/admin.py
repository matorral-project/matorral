from django.contrib import admin
from django.db.models import F, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.sprints.models import Sprint


@admin.register(Sprint)
class SprintAdmin(admin.ModelAdmin):
    list_display = [
        "key",
        "name",
        "workspace",
        "status",
        "start_date",
        "end_date",
        "owner",
    ]
    list_filter = ["status", "workspace"]
    search_fields = ["key", "name"]
    raw_id_fields = ["workspace", "owner"]
    readonly_fields = [
        "key",
        "committed_points",
        "completed_points",
        "created_at",
        "updated_at",
    ]
    ordering = ["-start_date"]
    actions = ["set_created_by_from_owner"]

    @admin.action(description=_("Set created_by from owner"))
    def set_created_by_from_owner(self, request: HttpRequest, queryset: QuerySet[Sprint]) -> None:
        updated = queryset.filter(owner__isnull=False).update(created_by=F("owner"))
        self.message_user(
            request,
            _("%(count)d sprint(s) had created_by set from owner.") % {"count": updated},
        )
