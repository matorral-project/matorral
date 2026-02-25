from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "date_joined",
        "terms_accepted_at",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    readonly_fields = ("terms_accepted_at",)
    search_fields = ("email",)
    ordering = ("-date_joined",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Extra Fields",
            {
                "fields": (
                    "avatar",
                    "language",
                    "timezone",
                    "terms_accepted_at",
                )
            },
        ),
    )
