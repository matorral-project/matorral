import hashlib
import uuid
from functools import cached_property

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.users.managers import UserManager
from apps.users.validators import validate_profile_picture

from allauth.account.models import EmailAddress


def _get_avatar_filename(instance, filename):
    """Use random filename prevent overwriting existing files & to fix caching issues."""
    return f"profile-pictures/{uuid.uuid4()}.{filename.split('.')[-1]}"


class User(AbstractUser):
    """
    Add additional fields to the user model here.
    """

    avatar = models.FileField(
        upload_to=_get_avatar_filename,
        blank=True,
        validators=[validate_profile_picture],
    )
    language = models.CharField(max_length=10, blank=True, null=True)
    timezone = models.CharField(max_length=100, blank=True, default="")
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    onboarding_completed = models.BooleanField(
        default=False,
        help_text=_("User has completed or dismissed onboarding checklist"),
    )
    onboarding_progress = models.JSONField(
        default=dict,
        help_text=_("Tracks onboarding progress: {demo_explored: bool, ...}"),
    )

    objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name()} <{self.email or self.username}>"

    def get_display_name(self) -> str:
        if self.get_full_name().strip():
            return self.get_full_name()
        return self.email or self.username

    @property
    def avatar_url(self) -> str:
        if self.avatar:
            return self.avatar.url
        return f"https://www.gravatar.com/avatar/{self.gravatar_id}?s=128&d=identicon"

    @property
    def gravatar_id(self) -> str:
        # https://en.gravatar.com/site/implement/hash/
        return hashlib.md5(self.email.lower().strip().encode("utf-8")).hexdigest()

    @cached_property
    def has_confirmed_email_address(self) -> bool:
        try:
            email_obj = EmailAddress.objects.get_for_user(self, self.email)
            return email_obj.verified
        except EmailAddress.DoesNotExist:
            return False
