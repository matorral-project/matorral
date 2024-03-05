from django.test import TestCase

from matorral.users.tests.factories import UserFactory


class TestUser(TestCase):

    def setUp(self):
        self.user = UserFactory.create(username="testuser")

    def test__str__(self):
        self.assertEqual(self.user.__str__(), "testuser")  # This is the default username for self.make_user()

    def test_get_absolute_url(self):
        self.assertEqual(self.user.get_absolute_url(), "/users/testuser/")
