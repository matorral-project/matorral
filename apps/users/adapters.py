from django.utils.translation import gettext_lazy as _

from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email, user_field


class UserEmailAsUsernameAdapter(DefaultAccountAdapter):
    def __init__(self, request=None):
        super().__init__(request)
        self.error_messages["email_taken"] = _("Coldn't create your account.")

    def populate_username(self, request, user):
        user_field(user, app_settings.USER_MODEL_USERNAME_FIELD, user_email(user))
