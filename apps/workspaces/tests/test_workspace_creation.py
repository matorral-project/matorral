from django.test import TestCase

from apps.users.models import CustomUser
from apps.workspaces.helpers import create_default_workspace_for_user
from apps.workspaces.models import Membership, Workspace
from apps.workspaces.roles import ROLE_ADMIN


class DefaultWorkspaceCreationTest(TestCase):
    def test_workspace_created_for_new_user(self):
        user = CustomUser.objects.create(username="alice@example.com", email="alice@example.com")
        initial_count = Workspace.objects.count()
        create_default_workspace_for_user(user)

        self.assertEqual(Workspace.objects.count(), initial_count + 1)

    def test_user_is_admin_of_created_workspace(self):
        user = CustomUser.objects.create(username="bob@example.com", email="bob@example.com")
        create_default_workspace_for_user(user)

        workspace = Workspace.objects.filter(members=user).first()
        self.assertIsNotNone(workspace)

        membership = Membership.objects.get(workspace=workspace, user=user)
        self.assertEqual(membership.role, ROLE_ADMIN)

    def test_two_users_get_separate_workspaces(self):
        user1 = CustomUser.objects.create(username="user1@example.com", email="user1@example.com")
        user2 = CustomUser.objects.create(username="user2@example.com", email="user2@example.com")

        create_default_workspace_for_user(user1)
        create_default_workspace_for_user(user2)

        ws1 = Workspace.objects.filter(members=user1).first()
        ws2 = Workspace.objects.filter(members=user2).first()

        self.assertIsNotNone(ws1)
        self.assertIsNotNone(ws2)
        self.assertNotEqual(ws1, ws2)
