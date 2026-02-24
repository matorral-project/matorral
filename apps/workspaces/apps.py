from django.apps import AppConfig


class WorkspacesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.workspaces"
    label = "workspaces"

    def ready(self):
        import apps.workspaces.signals  # noqa: F401
