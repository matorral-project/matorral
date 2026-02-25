from django.utils import timezone

from apps.users.models import User

import factory


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}@example.com")
    email = factory.LazyAttribute(lambda obj: obj.username)
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    terms_accepted_at = factory.LazyFunction(timezone.now)
    onboarding_completed = False
    onboarding_progress = factory.Dict({})

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", None)
        user = super()._create(model_class, *args, **kwargs)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user
