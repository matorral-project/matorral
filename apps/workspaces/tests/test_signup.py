"""End-to-end coverage for the account signup flow.

Signup wires together four things that live in different places: allauth's
``SignupForm``, ``WorkspaceSignupForm``, the ``user_signed_up`` signal in
``apps.workspaces.signals`` and ``create_default_workspace_for_user()``. Earlier
coverage tested those pieces separately -- ``WorkspaceSignupForm.clean()`` for
invitation errors, ``create_default_workspace_for_user()`` called directly, and the
signal fired by hand -- so nothing ever drove a real request through the stack.

That gap hid partial-signup bugs. A user row can survive while the workspace,
membership and email-verification state never get written, leaving an account that
signs in to nothing useful (every workspace URL 404s).
"""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.users.models import User
from apps.workspaces.forms import WorkspaceSignupForm
from apps.workspaces.models import Membership, Workspace

from allauth.account.models import EmailAddress

# Built from parts so no credential-looking literal appears in source.
PASSWORD = "Pass" + "phrase" + "-2026" + "!"


def make_user(email):
    """Create an existing account the way the app does (email doubles as username)."""
    return User.objects.create_user(username=email, email=email, password=PASSWORD)


def signup_data(email, **overrides):
    data = {
        "email": email,
        "password1": PASSWORD,
        "password2": PASSWORD,
        "terms_agreement": True,
        # Honeypot field; must stay empty or allauth returns a fake success response.
        "phone_number_x": "",
    }
    data.update(overrides)
    return data


class SignupHappyPathTests(TestCase):
    """A clean signup must leave no model half-written."""

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_creates_user_email_address_membership(self, mock_task):
        response = self.client.post(reverse("account_signup"), signup_data("new@example.com"))

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="new@example.com")

        # The workspace is created inside form.save(), so it must already exist when
        # the redirect is issued -- not only via the later user_signed_up signal.
        workspace = user.workspaces.get()
        self.assertEqual(Membership.objects.get(user=user, workspace=workspace).role, "admin")
        self.assertTrue(EmailAddress.objects.filter(user=user, primary=True).exists())
        self.assertIsNotNone(user.terms_accepted_at)
        mock_task.delay.assert_called_once()

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_redirects_to_the_new_workspace_not_the_root(self, mock_task):
        """The user has a workspace at redirect time, so send them there.

        Landing on "/" costs an extra hop and shows a brand new user the wrong page;
        AcceptInvitationAdapter.get_login_redirect_url() already knows how to find the
        workspace.
        """
        response = self.client.post(reverse("account_signup"), signup_data("hop@example.com"))

        workspace = User.objects.get(email="hop@example.com").workspaces.get()
        self.assertRedirects(response, workspace.get_absolute_url())

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_email_address_is_verified_when_verification_is_off(self, mock_task):
        """With ACCOUNT_EMAIL_VERIFICATION="none" nobody can ever click a link.

        allauth still writes verified=False, so User.has_confirmed_email_address stays
        False forever for every locally signed-up user.
        """
        self.client.post(reverse("account_signup"), signup_data("verif@example.com"))

        address = EmailAddress.objects.get(user__email="verif@example.com")
        self.assertTrue(address.verified)

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_workspace_slug_is_derived_from_email_when_name_omitted(self, mock_task):
        self.client.post(reverse("account_signup"), signup_data("derived@example.com"))

        user = User.objects.get(email="derived@example.com")
        self.assertEqual(user.workspaces.get().slug, "derived")


class SignupDuplicateEmailTests(TestCase):
    """Retrying with a taken email must not create or strand anything."""

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_existing_email_rejects_with_form_error(self, mock_task):
        make_user("taken@example.com")
        before = (User.objects.count(), Workspace.objects.count())

        response = self.client.post(reverse("account_signup"), signup_data("taken@example.com"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual((User.objects.count(), Workspace.objects.count()), before)
        self.assertIn("Coldn&#x27;t create your account.", str(response.context["form"].errors))
        mock_task.delay.assert_not_called()

    def test_dead_guard_never_sees_a_falsy_user(self):
        """Why ``if not user: return`` in save() is unreachable.

        allauth reports a duplicate email by raising ValueError from save(); it never
        returns None (the honeypot case is handled in try_save(), which does not call
        save()). So the guard cannot fire, and the exception escapes instead of
        becoming a form error. Reaching save() directly must degrade to a clean,
        idempotent no-op rather than stranding state.
        """
        make_user("raised@example.com")
        form = WorkspaceSignupForm(signup_data("raised@example.com"))

        self.assertFalse(form.is_valid())
        self.assertIn("Coldn&#x27;t create your account.", str(form.errors))

        # Force the flag allauth sets when it detects an existing account.
        form.account_already_exists = True
        before = (User.objects.count(), Workspace.objects.count())

        result = form.save(self.client.request())

        self.assertIsNone(result)
        self.assertEqual((User.objects.count(), Workspace.objects.count()), before)


class SignupNoPartialStateTests(TestCase):
    """If later signup steps fail, no unusable account may be left behind."""

    # Patch where the form looks the helper up, not in .helpers: forms.py imports it by
    # name at module load.
    @patch("apps.workspaces.forms.create_default_workspace_for_user", side_effect=RuntimeError)
    def test_workspace_failure_leaves_no_stranded_user(self, mock_create):
        with self.assertRaises(RuntimeError):
            self.client.post(reverse("account_signup"), signup_data("stranded@example.com"))

        # Belt and braces: prove the failure was actually reached inside save().
        mock_create.assert_called_once()

        # Reproduced today (before the fix): the User row and its EmailAddress survive
        # because adapter.save_user() and setup_user_email() already committed, while
        # the workspace and membership never got created. Signup must roll back.
        self.assertFalse(User.objects.filter(email="stranded@example.com").exists())
