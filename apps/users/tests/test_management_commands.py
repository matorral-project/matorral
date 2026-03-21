from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.users.factories import UserFactory


class TestMakeSuperuserCommand(SimpleTestCase):
    @patch("apps.users.management.commands.make_superuser.get_user_model")
    def test_make_superuser_promotes_existing_user(self, mock_get_user_model):
        user = UserFactory.build(email="alice@example.com", username="alice@example.com")
        user.is_staff = False
        user.is_superuser = False
        user.save = MagicMock()

        user_model = MagicMock()
        user_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        user_model.objects.get.return_value = user
        mock_get_user_model.return_value = user_model

        stdout = StringIO()
        call_command("make_superuser", user.email, stdout=stdout)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        user.save.assert_called_once_with(update_fields=["is_staff", "is_superuser"])
        self.assertIn("is now a staff member and superuser", stdout.getvalue())

    @patch("apps.users.management.commands.make_superuser.get_user_model")
    def test_make_superuser_raises_for_missing_user(self, mock_get_user_model):
        user_model = MagicMock()
        user_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        user_model.objects.get.side_effect = user_model.DoesNotExist
        mock_get_user_model.return_value = user_model

        with self.assertRaises(CommandError):
            call_command("make_superuser", "missing@example.com")
