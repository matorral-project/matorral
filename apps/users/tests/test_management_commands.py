from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.users.factories import UserFactory


class TestMakeSuperuserCommand(TestCase):
    def test_make_superuser_promotes_existing_user(self):
        user = UserFactory(is_staff=False, is_superuser=False)
        stdout = StringIO()

        call_command("make_superuser", user.email, stdout=stdout)

        user.refresh_from_db()
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertIn("is now a staff member and superuser", stdout.getvalue())

    def test_make_superuser_user_not_found_raises_command_error(self):
        with self.assertRaisesMessage(CommandError, 'No user found with email "unknown@example.com"'):
            call_command("make_superuser", "unknown@example.com")
