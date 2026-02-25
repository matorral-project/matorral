from django.apps import AppConfig


class UserConfig(AppConfig):
    name = "apps.users"
    label = "users"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from apps.users import signals  # noqa
