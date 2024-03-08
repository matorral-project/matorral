from matorral.workspaces.models import Workspace


def create_default_workspace(*args, **kwargs):
    user = kwargs["instance"]

    if kwargs["created"] and Workspace.objects.count() == 0:
        workspace = Workspace.objects.create(name="Default Workspace", slug="default", owner=user)
        workspace.members.add(user)
