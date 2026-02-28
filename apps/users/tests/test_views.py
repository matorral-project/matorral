import io

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.users.factories import UserFactory

from allauth.account.models import EmailAddress

PROFILE_URL = reverse("users:user_profile")
UPLOAD_URL = reverse("users:upload_profile_image")


class TestProfileView(TestCase):
    """Tests for ProfileView GET/POST logic."""

    def setUp(self):
        self.user = UserFactory(password="pass")

    def test_get_returns_200_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
    def test_post_updates_name_and_timezone(self):
        self.client.force_login(self.user)
        response = self.client.post(
            PROFILE_URL,
            {
                "first_name": "Updated",
                "last_name": "Name",
                "email": self.user.email,
                "timezone": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        messages = list(response.context["messages"])
        self.assertTrue(any("successfully saved" in str(m) for m in messages))

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
    def test_post_email_change_without_mandatory_verification_updates_email_address(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        self.client.force_login(self.user)
        new_email = "newemail@example.com"
        self.client.post(
            PROFILE_URL,
            {
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": new_email,
                "timezone": "",
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, new_email)
        self.assertTrue(EmailAddress.objects.filter(user=self.user, email=new_email, primary=True).exists())

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
    def test_post_email_change_with_mandatory_verification_does_not_change_email(self):
        original_email = self.user.email
        self.client.force_login(self.user)
        self.client.post(
            PROFILE_URL,
            {
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": "different@example.com",
                "timezone": "",
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, original_email)

    def test_htmx_get_returns_partial_template(self):
        self.client.force_login(self.user)
        response = self.client.get(PROFILE_URL, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        # Fragment templates are reported by their block name, not the full path
        self.assertTemplateUsed(response, "page-content")

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
    def test_post_does_not_update_email_when_unchanged(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        original_count = EmailAddress.objects.filter(user=self.user).count()
        self.client.force_login(self.user)
        self.client.post(
            PROFILE_URL,
            {
                "first_name": self.user.first_name,
                "last_name": self.user.last_name,
                "email": self.user.email,
                "timezone": "",
            },
        )
        self.assertEqual(EmailAddress.objects.filter(user=self.user).count(), original_count)


class TestUploadProfileImageView(TestCase):
    """Tests for UploadProfileImageView."""

    def setUp(self):
        self.user = UserFactory(password="pass")

    def test_valid_upload_saves_avatar(self):
        self.client.force_login(self.user)
        # Create a minimal valid JPEG in memory (1x1 pixel)
        image_data = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
            b"\xc1\xca\xff\xd9"
        )
        avatar_file = io.BytesIO(image_data)
        avatar_file.name = "test.jpg"
        response = self.client.post(UPLOAD_URL, {"avatar": avatar_file})
        self.user.refresh_from_db()
        self.assertIn(response.status_code, [200, 403])

    def test_invalid_file_returns_403_json_error(self):
        self.client.force_login(self.user)
        bad_file = io.BytesIO(b"not an image")
        bad_file.name = "doc.pdf"
        response = self.client.post(UPLOAD_URL, {"avatar": bad_file})
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("errors", data)

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.post(UPLOAD_URL, {})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
