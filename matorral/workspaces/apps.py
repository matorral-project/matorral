from django.apps import AppConfig
from django.db.models.signals import post_save


class WorkspacesConfig(AppConfig):
    name = "matorral.workspaces"

    def ready(self):
        from matorral.workspaces import signals
        from matorral.users.models import User

        post_save.connect(signals.create_default_workspace, sender=User)
