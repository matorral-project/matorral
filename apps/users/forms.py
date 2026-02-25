from zoneinfo import available_timezones

from django import forms
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from allauth.socialaccount.forms import SignupForm

from .models import User
from .validators import validate_profile_picture


class UserChangeForm(BaseUserChangeForm):
    email = forms.EmailField(label=_("Email"), required=True)
    timezone = forms.ChoiceField(label=_("Time Zone"), required=False)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "timezone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        timezone = self.fields.get("timezone")
        timezone.choices = [("", _("Not Set"))] + sorted((tz, tz) for tz in available_timezones())


class UploadAvatarForm(forms.Form):
    avatar = forms.FileField(validators=[validate_profile_picture])


class CustomSocialSignupForm(SignupForm):
    terms_agreement = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prevent_enumeration = False
        link = '<a class="link" href={} target="_blank">{}</a>'.format(
            reverse("landing_pages:terms"),
            _("Terms and Conditions"),
        )
        self.fields["terms_agreement"].label = mark_safe(_("I agree to the {terms_link}").format(terms_link=link))

    def save(self, request):
        user = super().save(request)
        if user:
            user.terms_accepted_at = timezone.now()
            user.save(update_fields=["terms_accepted_at"])
        return user
