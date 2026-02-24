from django.contrib import admin
from django.db.models import F, QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Project, ProjectStatus


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "key", "workspace", "status_badge", "lead", "created_at"]
    list_display_links = ["name", "key"]
    list_filter = ["status", "workspace"]
    list_select_related = ["workspace", "lead"]
    list_per_page = 20
    search_fields = ["name", "key", "description", "workspace__name"]
    autocomplete_fields = ["workspace", "lead"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    actions = [
        "make_active",
        "make_completed",
        "make_archived",
        "make_draft",
        "reset_created_by",
        "set_created_by_from_lead",
    ]
    empty_value_display = "—"

    fieldsets = (
        (
            None,
            {
                "fields": ("workspace", "name", "key", "description"),
            },
        ),
        (
            _("Status & Assignment"),
            {
                "fields": ("status", "lead"),
            },
        ),
        (
            _("Timestamps"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    readonly_fields = ["created_at", "updated_at"]

    @admin.display(description=_("Status"), ordering="status")
    def status_badge(self, obj: Project) -> str:
        """Display status with color-coded badge."""
        colors = {
            ProjectStatus.DRAFT: "#6b7280",  # gray
            ProjectStatus.ACTIVE: "#22c55e",  # green
            ProjectStatus.COMPLETED: "#3b82f6",  # blue
            ProjectStatus.ARCHIVED: "#f59e0b",  # amber
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: 500;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.action(description=_("Mark selected projects as Active"))
    def make_active(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.set_active()
        self.message_user(request, _("%(count)d project(s) marked as active.") % {"count": updated})

    @admin.action(description=_("Mark selected projects as Completed"))
    def make_completed(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.set_completed()
        self.message_user(request, _("%(count)d project(s) marked as completed.") % {"count": updated})

    @admin.action(description=_("Mark selected projects as Archived"))
    def make_archived(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.set_archived()
        self.message_user(request, _("%(count)d project(s) marked as archived.") % {"count": updated})

    @admin.action(description=_("Mark selected projects as Draft"))
    def make_draft(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.set_draft()
        self.message_user(request, _("%(count)d project(s) marked as draft.") % {"count": updated})

    @admin.action(description=_("Reset created_by to None (mark as system-created)"))
    def reset_created_by(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.update(created_by=None)
        self.message_user(
            request,
            _("%(count)d project(s) had created_by reset.") % {"count": updated},
        )

    @admin.action(description=_("Set created_by from lead"))
    def set_created_by_from_lead(self, request: HttpRequest, queryset: QuerySet[Project]) -> None:
        updated = queryset.filter(lead__isnull=False).update(created_by=F("lead"))
        self.message_user(
            request,
            _("%(count)d project(s) had created_by set from lead.") % {"count": updated},
        )
