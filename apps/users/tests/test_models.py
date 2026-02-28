import hashlib
from unittest.mock import MagicMock

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.users.factories import UserFactory
from apps.users.validators import ProfilePictureValidator

from allauth.account.models import EmailAddress


class TestUserModel(TestCase):
    """Tests for custom User model methods and properties."""

    def test_get_display_name_returns_full_name(self):
        user = UserFactory(first_name="Alice", last_name="Smith")
        self.assertEqual(user.get_display_name(), "Alice Smith")

    def test_get_display_name_falls_back_to_email(self):
        user = UserFactory(first_name="", last_name="")
        self.assertEqual(user.get_display_name(), user.email)

    def test_avatar_url_returns_gravatar_when_no_avatar(self):
        user = UserFactory()
        url = user.avatar_url
        self.assertIn("gravatar.com/avatar/", url)
        self.assertIn(user.gravatar_id, url)

    def test_gravatar_id_is_md5_of_normalized_email(self):
        user = UserFactory(email="  Test@Example.COM  ")
        expected = hashlib.md5(b"test@example.com").hexdigest()
        self.assertEqual(user.gravatar_id, expected)

    def test_has_confirmed_email_address_true(self):
        user = UserFactory()
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        # Clear cached_property so it re-queries
        if "has_confirmed_email_address" in user.__dict__:
            del user.__dict__["has_confirmed_email_address"]
        self.assertTrue(user.has_confirmed_email_address)

    def test_has_confirmed_email_address_false(self):
        user = UserFactory()
        self.assertFalse(user.has_confirmed_email_address)


class TestProfilePictureValidator(TestCase):
    """Tests for ProfilePictureValidator extension and size checks."""

    def _make_file(self, name, size):
        f = MagicMock()
        f.name = name
        f.size = size
        return f

    def test_valid_jpg_passes(self):
        validator = ProfilePictureValidator()
        f = self._make_file("photo.jpg", 1024)
        validator(f)  # should not raise

    def test_valid_webp_passes(self):
        validator = ProfilePictureValidator()
        f = self._make_file("photo.webp", 1024)
        validator(f)  # should not raise

    def test_uppercase_extension_passes(self):
        validator = ProfilePictureValidator()
        f = self._make_file("photo.JPG", 1024)
        validator(f)  # should not raise

    def test_invalid_extension_raises(self):
        validator = ProfilePictureValidator()
        f = self._make_file("document.pdf", 1024)
        with self.assertRaises(ValidationError):
            validator(f)

    def test_file_over_5mb_raises(self):
        validator = ProfilePictureValidator()
        f = self._make_file("photo.jpg", 5 * 1024**2 + 1)
        with self.assertRaises(ValidationError):
            validator(f)

    def test_file_at_exact_limit_passes(self):
        validator = ProfilePictureValidator()
        f = self._make_file("photo.jpg", 5 * 1024**2)
        validator(f)  # should not raise
