from unittest.mock import patch

from django.test import TestCase

from apps.projects.factories import ProjectFactory
from apps.sprints.factories import SprintFactory
from apps.sprints.models import SprintStatus
from apps.users.factories import UserFactory
from apps.workspaces.factories import InvitationFactory, MembershipFactory, WorkspaceFactory
from apps.workspaces.helpers import (
    create_default_workspace_for_user,
    get_default_workspace_for_user,
    get_default_workspace_name_for_user,
    get_onboarding_status,
    get_open_invitations_for_user,
    get_user_dashboard_data,
)
from apps.workspaces.models import Membership, Workspace
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER

from allauth.account.models import EmailAddress


class TestGetDefaultWorkspaceNameForUser(TestCase):
    def test_uses_full_name_when_available(self):
        user = UserFactory(first_name="Alice", last_name="Smith", email="alice@example.com")
        name = get_default_workspace_name_for_user(user)
        self.assertEqual(name, "Alice Smith")

    def test_uses_email_prefix_when_no_full_name(self):
        user = UserFactory(first_name="", last_name="", email="bob@example.com")
        name = get_default_workspace_name_for_user(user)
        self.assertEqual(name, "Bob")

    def test_returns_my_workspace_when_name_empty(self):
        # If email is also empty, falls back to "My Workspace"
        user = UserFactory(first_name="", last_name="", email="@example.com")
        name = get_default_workspace_name_for_user(user)
        self.assertEqual(name, "My Workspace")


class TestGetDefaultWorkspaceForUser(TestCase):
    def test_returns_first_workspace_when_user_has_one(self):
        user = UserFactory()
        workspace = WorkspaceFactory()
        MembershipFactory(workspace=workspace, user=user, role=ROLE_MEMBER)
        result = get_default_workspace_for_user(user)
        self.assertEqual(result, workspace)

    def test_returns_none_when_user_has_no_workspaces(self):
        user = UserFactory()
        result = get_default_workspace_for_user(user)
        self.assertIsNone(result)


class TestCreateDefaultWorkspaceForUser(TestCase):
    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_creates_workspace_with_admin_membership(self, mock_task):
        mock_task.delay.return_value = None
        user = UserFactory(first_name="Carol", last_name="", email="carol@example.com")
        workspace = create_default_workspace_for_user(user)
        self.assertIsNotNone(workspace)
        self.assertIsInstance(workspace, Workspace)
        self.assertTrue(Membership.objects.filter(workspace=workspace, user=user, role=ROLE_ADMIN).exists())

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_uses_provided_workspace_name(self, mock_task):
        mock_task.delay.return_value = None
        user = UserFactory()
        workspace = create_default_workspace_for_user(user, workspace_name="Custom Name")
        self.assertEqual(workspace.name, "Custom Name")

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_derives_name_from_user_when_not_provided(self, mock_task):
        mock_task.delay.return_value = None
        user = UserFactory(first_name="Dave", last_name="Jones", email="dave@example.com")
        workspace = create_default_workspace_for_user(user)
        self.assertEqual(workspace.name, "Dave Jones")

    @patch("apps.workspaces.helpers.create_demo_project_task")
    def test_triggers_demo_project_task(self, mock_task):
        mock_task.delay.return_value = None
        user = UserFactory()
        workspace = create_default_workspace_for_user(user)
        mock_task.delay.assert_called_once_with(workspace.pk, user.pk)


class TestGetOnboardingStatus(TestCase):
    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.user = UserFactory(onboarding_completed=False, onboarding_progress={})

    def test_returns_should_show_false_when_onboarding_completed(self):
        self.user.onboarding_completed = True
        self.user.save()
        result = get_onboarding_status(self.user, self.workspace)
        self.assertFalse(result["should_show"])
        self.assertEqual(result["pending_count"], 0)

    def test_returns_steps_with_should_show_true_when_nothing_done(self):
        result = get_onboarding_status(self.user, self.workspace)
        self.assertTrue(result["should_show"])
        self.assertEqual(len(result["steps"]), 4)
        self.assertGreater(result["pending_count"], 0)

    def test_explore_demo_step_completed_via_progress_flag(self):
        self.user.onboarding_progress = {"demo_explored": True}
        self.user.save()
        result = get_onboarding_status(self.user, self.workspace)
        explore_step = next(s for s in result["steps"] if s["key"] == "explore_demo")
        self.assertTrue(explore_step["completed"])

    def test_create_project_step_completed_when_user_has_project(self):
        ProjectFactory(workspace=self.workspace, created_by=self.user)
        result = get_onboarding_status(self.user, self.workspace)
        project_step = next(s for s in result["steps"] if s["key"] == "create_project")
        self.assertTrue(project_step["completed"])

    def test_invite_teammates_step_completed_when_invitation_exists(self):
        InvitationFactory(workspace=self.workspace)
        result = get_onboarding_status(self.user, self.workspace)
        invite_step = next(s for s in result["steps"] if s["key"] == "invite_teammates")
        self.assertTrue(invite_step["completed"])

    def test_create_sprint_step_completed_when_sprint_exists(self):
        creator = UserFactory()
        SprintFactory(workspace=self.workspace, created_by=creator)
        result = get_onboarding_status(self.user, self.workspace)
        sprint_step = next(s for s in result["steps"] if s["key"] == "create_sprint")
        self.assertTrue(sprint_step["completed"])

    def test_marks_user_onboarding_completed_when_all_steps_done(self):
        self.user.onboarding_progress = {"demo_explored": True}
        self.user.save()
        creator = UserFactory()
        ProjectFactory(workspace=self.workspace, created_by=self.user)
        InvitationFactory(workspace=self.workspace)
        SprintFactory(workspace=self.workspace, created_by=creator)
        get_onboarding_status(self.user, self.workspace)
        self.user.refresh_from_db()
        self.assertTrue(self.user.onboarding_completed)

    def test_handles_none_workspace(self):
        result = get_onboarding_status(self.user, None)
        self.assertTrue(result["should_show"])
        for step in result["steps"]:
            self.assertIsNone(step["url"])

    def test_completed_count_is_correct(self):
        self.user.onboarding_progress = {"demo_explored": True}
        self.user.save()
        result = get_onboarding_status(self.user, self.workspace)
        self.assertEqual(result["completed_count"], 1)
        self.assertEqual(result["pending_count"], 3)


class TestGetOpenInvitationsForUser(TestCase):
    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.user = UserFactory()

    def test_returns_empty_when_user_has_no_email_addresses(self):
        result = get_open_invitations_for_user(self.user)
        self.assertEqual(result, [])

    def test_returns_matching_open_invitation(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        InvitationFactory(workspace=self.workspace, email=self.user.email)
        result = get_open_invitations_for_user(self.user)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["email"], self.user.email)

    def test_excludes_accepted_invitations(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        InvitationFactory(workspace=self.workspace, email=self.user.email, is_accepted=True, accepted_by=self.user)
        result = get_open_invitations_for_user(self.user)
        self.assertEqual(result, [])

    def test_excludes_workspaces_user_already_belongs_to(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_MEMBER)
        InvitationFactory(workspace=self.workspace, email=self.user.email)
        result = get_open_invitations_for_user(self.user)
        self.assertEqual(result, [])

    def test_marks_verified_email_as_verified(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        InvitationFactory(workspace=self.workspace, email=self.user.email)
        result = get_open_invitations_for_user(self.user)
        self.assertTrue(result[0]["verified"])

    def test_marks_unverified_email_as_not_verified(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=False, primary=True)
        InvitationFactory(workspace=self.workspace, email=self.user.email)
        result = get_open_invitations_for_user(self.user)
        self.assertFalse(result[0]["verified"])

    def test_workspace_name_is_included_in_result(self):
        EmailAddress.objects.create(user=self.user, email=self.user.email, verified=True, primary=True)
        InvitationFactory(workspace=self.workspace, email=self.user.email)
        result = get_open_invitations_for_user(self.user)
        self.assertEqual(result[0]["workspace_name"], self.workspace.name)


class TestGetUserDashboardData(TestCase):
    def setUp(self):
        self.workspace = WorkspaceFactory()
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_MEMBER)

    def test_returns_expected_keys(self):
        result = get_user_dashboard_data(self.user, self.workspace)
        expected_keys = {
            "active_sprint",
            "sprint_progress",
            "in_progress_issues",
            "in_review_issues",
            "ready_issues",
            "blocked_issues",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_returns_none_sprint_when_no_active_sprint(self):
        result = get_user_dashboard_data(self.user, self.workspace)
        self.assertIsNone(result["active_sprint"])
        self.assertIsNone(result["sprint_progress"])

    def test_returns_active_sprint_when_one_exists(self):
        sprint = SprintFactory(workspace=self.workspace, status=SprintStatus.ACTIVE)
        result = get_user_dashboard_data(self.user, self.workspace)
        self.assertEqual(result["active_sprint"], sprint)

    def test_issue_lists_are_lists(self):
        result = get_user_dashboard_data(self.user, self.workspace)
        self.assertIsInstance(result["in_progress_issues"], list)
        self.assertIsInstance(result["in_review_issues"], list)
        self.assertIsInstance(result["ready_issues"], list)
        self.assertIsInstance(result["blocked_issues"], list)
