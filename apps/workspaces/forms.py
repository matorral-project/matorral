from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from allauth.account.forms import SignupForm

from .helpers import create_default_workspace_for_user, get_next_unique_workspace_slug, get_open_invitations_for_user
from .limits import LimitExceededError, check_invitation_limit, check_member_limit
from .models import Invitation, Membership, Workspace


class WorkspaceSignupForm(SignupForm):
    invitation_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    workspace_name = forms.CharField(
        label=_("Workspace Name (Optional)"),
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": _("Workspace Name (Optional)")}),
        required=False,
    )
    terms_agreement = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = ""
        link = '<a class="link" href={} target="_blank">{}</a>'.format(
            reverse("landing_pages:terms"),
            _("Terms and Conditions"),
        )
        self.fields["terms_agreement"].label = mark_safe(_("I agree to the {terms_link}").format(terms_link=link))

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            self._clean_workspace_name(cleaned_data)
            self._clean_invitation_email(cleaned_data)
        return cleaned_data

    def _clean_workspace_name(self, cleaned_data):
        workspace_name = cleaned_data.get("workspace_name")
        invitation_id = cleaned_data.get("invitation_id")
        if not invitation_id and not workspace_name:
            email = cleaned_data.get("email")
            if email is not None:
                workspace_name = f"{email.split('@')[0]}"
        elif invitation_id:
            assert not workspace_name
        cleaned_data["workspace_name"] = workspace_name

    def _clean_invitation_email(self, cleaned_data):
        invitation_id = cleaned_data.get("invitation_id")
        if invitation_id:
            try:
                invite = Invitation.objects.get(id=invitation_id)
            except (Invitation.DoesNotExist, ValidationError):
                raise forms.ValidationError(
                    _(
                        "That invitation could not be found. "
                        "Please double check your invitation link or sign in to continue."
                    )
                ) from None

            if invite.is_accepted:
                raise forms.ValidationError(
                    _(
                        "It looks like that invitation link has expired. "
                        "Please request a new invitation or sign in to continue."
                    )
                )

            email = cleaned_data.get("email")
            if invite.email.lower() != email:
                raise forms.ValidationError(
                    _("You must sign up with the email address that the invitation was sent to.")
                )

    def save(self, request):
        invitation_id = self.cleaned_data["invitation_id"]
        workspace_name = self.cleaned_data["workspace_name"]
        user = super().save(request)

        if not user:
            return

        user.terms_accepted_at = timezone.now()
        user.save(update_fields=["terms_accepted_at"])

        if not invitation_id and not get_open_invitations_for_user(user):
            create_default_workspace_for_user(user, workspace_name)

        return user


class WorkspaceChangeForm(forms.ModelForm):
    slug = forms.SlugField(
        required=False,
        label=_("Slug"),
        help_text=_("A unique ID for your workspace. No spaces are allowed!"),
    )

    class Meta:
        model = Workspace
        fields = ("name", "slug")
        labels = {"name": _("Name")}
        help_texts = {"name": _("Your workspace name.")}

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        if not slug or slug.strip() == "":
            slug = get_next_unique_workspace_slug(self.cleaned_data["name"])
        return slug


class InvitationForm(forms.ModelForm):
    def __init__(self, workspace, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace

    def clean(self):
        cleaned_data = super().clean()
        try:
            check_member_limit(self.workspace)
        except LimitExceededError as e:
            raise ValidationError(str(e)) from None
        try:
            check_invitation_limit(self.workspace)
        except LimitExceededError as e:
            raise ValidationError(str(e)) from None
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Invitation.objects.filter(workspace=self.workspace, email__iexact=email, is_accepted=False):
            raise ValidationError(
                _(
                    'There is already a pending invitation for {}. You can resend it by clicking "Resend Invitation".'
                ).format(email)
            )
        if Membership.objects.filter(workspace=self.workspace, user__email__iexact=email).exists():
            raise ValidationError(_("{email} is already a member of this workspace.").format(email=email))
        return email

    class Meta:
        model = Invitation
        fields = ("email", "role")


class MembershipForm(forms.ModelForm):
    class Meta:
        model = Membership
        fields = ("role",)
