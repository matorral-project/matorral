from apps.projects.models import Project, ProjectStatus
from apps.workspaces.factories import WorkspaceFactory

import factory


class ProjectFactory(factory.django.DjangoModelFactory):
    """Factory for creating Project instances."""

    class Meta:
        model = Project

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"Project {n}")
    key = ""  # Let the model auto-generate
    description = ""
    status = ProjectStatus.DRAFT
    lead = None
