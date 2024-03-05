import factory

from matorral.workspaces.models import Workspace


class WorkspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workspace

    name = factory.Faker("name")
    slug = factory.Faker("slug")
