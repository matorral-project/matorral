from unittest.mock import patch

from django.test import TestCase

from apps.users.factories import UserFactory


class TestRemovePreviousPictureSignal(TestCase):
    @patch("apps.users.signals.default_storage")
    def test_old_avatar_deleted_when_avatar_changed(self, mock_storage):
        mock_storage.exists.return_value = True

        user = UserFactory()
        user.avatar = "profile-pictures/old_avatar.jpg"
        user.save(update_fields=["avatar"])  # first save: DB was empty → no deletion

        user.avatar = "profile-pictures/new_avatar.jpg"
        user.save(update_fields=["avatar"])  # second save: old != new → deletion

        mock_storage.delete.assert_called_once_with("profile-pictures/old_avatar.jpg")
