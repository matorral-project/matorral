from django.apps import AppConfig


class GenericUiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.generic_ui"
    label = "generic_ui"
