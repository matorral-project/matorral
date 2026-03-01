from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.users.factories import UserFactory
from apps.workspaces.models import Workspace

from allauth.account.signals import user_signed_up


class TestUserSignedUpSignal(TestCase):
    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_creates_default_workspace_when_no_invitation_and_no_workspace(self, mock_task):
        user = UserFactory()
        request = RequestFactory().get("/")
        request.session = {}

        user_signed_up.send(sender=user.__class__, request=request, user=user)

        self.assertTrue(user.workspaces.exists())
        self.assertIsInstance(user.workspaces.first(), Workspace)
        mock_task.delay.assert_called_once()
