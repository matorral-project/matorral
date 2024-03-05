import factory

from factory import fuzzy

from matorral.stories.models import Story, StoryState


class StoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Story

    title = factory.Faker("sentence", nb_words=4)
    description = factory.Faker("text")
    state = fuzzy.FuzzyChoice(StoryState.objects.all())
    points = factory.Faker("random_int", min=0, max=8)

    workspace = factory.SubFactory("matorral.workspaces.factories.WorkspaceFactory")
    requester = factory.SubFactory("matorral.users.tests.factories.UserFactory")
    assignee = factory.SubFactory("matorral.users.tests.factories.UserFactory")

    created_at = factory.Faker("date_time_this_decade")
    updated_at = factory.Faker("date_time_this_decade")
