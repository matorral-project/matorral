from django.contrib import admin

from .models import Invitation, Membership, Workspace


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at", "updated_at"]
    list_filter = ["created_at"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "workspace", "role", "created_at"]
    list_filter = ["workspace", "role"]
    search_fields = ["user__email"]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["id", "workspace", "email", "role", "is_accepted"]
    list_filter = ["workspace", "is_accepted"]
    search_fields = ["email"]
