from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views import View

from allauth.account import app_settings
from allauth.account.models import EmailAddress
from allauth.account.views import PasswordChangeView
from allauth.socialaccount.models import SocialAccount

from .forms import UploadAvatarForm, UserChangeForm
from .models import User


class ProfileView(LoginRequiredMixin, View):
    def get(self, request):
        form = UserChangeForm(instance=request.user)
        return render(request, self._template(request), self._context(request, form))

    def post(self, request):
        form = UserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user_before_update = User.objects.get(pk=user.pk)
            email_changed = user_before_update.email != user.email
            need_to_confirm_email = (
                email_changed
                and app_settings.EMAIL_VERIFICATION == app_settings.EmailVerificationMethod.MANDATORY
                and not user.has_confirmed_email_address
            )
            if need_to_confirm_email:
                new_email = user.email
                EmailAddress.objects.add_email(request, user, new_email, confirm=True)
                user.email = user_before_update.email
                form = UserChangeForm(instance=user)
            user.save()
            if email_changed and not need_to_confirm_email:
                new_email = user.email
                EmailAddress.objects.filter(user=user, primary=True).update(primary=False)
                new_addr, _created = EmailAddress.objects.get_or_create(
                    user=user, email=new_email, defaults={"primary": True, "verified": True}
                )
                if not new_addr.primary or not new_addr.verified:
                    new_addr.primary = True
                    new_addr.verified = True
                    new_addr.save(update_fields=["primary", "verified"])

            user_language = user.language

            if user_language and user_language != translation.get_language():
                translation.activate(user_language)

            if user.timezone != timezone.get_current_timezone():
                if user.timezone:
                    timezone.activate(user.timezone)
                else:
                    timezone.deactivate()

            messages.success(request, _("Your profile was successfully saved."))

        return render(request, self._template(request), self._context(request, form))

    def _template(self, request):
        return "account/profile.html#page-content" if request.htmx else "account/profile.html"

    def _context(self, request, form):
        return {
            "form": form,
            "active_tab": "profile",
            "page_title": _("Profile"),
            "now": timezone.now(),
            "current_tz": timezone.get_current_timezone(),
        }


class UploadProfileImageView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        user = request.user
        form = UploadAvatarForm(request.POST, request.FILES)
        if form.is_valid():
            user.avatar = request.FILES["avatar"]
            user.save()
            return HttpResponse(_("Your avatar was successfully uploaded."))

        str_errors = ", ".join(str(error) for key, errors in form.errors.items() for error in errors)
        return JsonResponse(status=403, data={"errors": str_errors})


class ConnectedAccountsView(LoginRequiredMixin, View):
    def get(self, request):
        template = "account/connected_accounts.html#page-content" if request.htmx else "account/connected_accounts.html"
        return render(
            request,
            template,
            {
                "active_tab": "connected_accounts",
                "page_title": _("Connected Accounts"),
                "social_accounts": SocialAccount.objects.filter(user=request.user),
            },
        )


class CustomPasswordChangeView(PasswordChangeView):
    """Custom password change view with HTMX partial rendering support."""

    def get_template_names(self):
        if self.request.htmx:
            return ["account/password_change.html#page-content"]
        return ["account/password_change.html"]
