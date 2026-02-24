from datetime import timedelta

from django.utils import timezone

from apps.sprints.models import Sprint, SprintStatus
from apps.workspaces.factories import WorkspaceFactory

import factory


class SprintFactory(factory.django.DjangoModelFactory):
    """Factory for creating Sprint instances."""

    class Meta:
        model = Sprint

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"Sprint {n}")
    key = ""  # Let the model auto-generate
    goal = ""
    status = SprintStatus.PLANNING
    start_date = factory.LazyFunction(lambda: timezone.now().date())
    end_date = factory.LazyAttribute(lambda o: o.start_date + timedelta(weeks=2))
    owner = None
    capacity = None
    committed_points = 0
    completed_points = 0
