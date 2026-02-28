from django.test import RequestFactory, TestCase

from apps.users.factories import UserFactory
from apps.workspaces.context_processors import default_workspace, onboarding_context
from apps.workspaces.factories import MembershipFactory, WorkspaceFactory
from apps.workspaces.roles import ROLE_ADMIN, ROLE_MEMBER


class TestOnboardingContextProcessor(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.workspace = WorkspaceFactory()
        self.user = UserFactory(onboarding_completed=False)
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_ADMIN)

    def _make_request(self, user=None, workspace=None):
        request = self.factory.get("/")
        if user is not None:
            request.user = user
        if workspace is not None:
            request.workspace = workspace
        return request

    def test_returns_pending_count_when_authenticated_with_workspace(self):
        request = self._make_request(user=self.user, workspace=self.workspace)
        context = onboarding_context(request)
        self.assertIn("onboarding_pending_count", context)
        self.assertIsInstance(context["onboarding_pending_count"], int)

    def test_returns_zero_when_no_user_attribute(self):
        request = self.factory.get("/")
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)

    def test_returns_zero_when_user_not_authenticated(self):
        from django.contrib.auth.models import AnonymousUser

        request = self._make_request(user=AnonymousUser(), workspace=self.workspace)
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)

    def test_returns_zero_when_no_workspace_attribute(self):
        request = self.factory.get("/")
        request.user = self.user
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)

    def test_returns_zero_when_workspace_is_none(self):
        request = self._make_request(user=self.user, workspace=None)
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)

    def test_returns_zero_when_onboarding_already_completed(self):
        self.user.onboarding_completed = True
        self.user.save()
        request = self._make_request(user=self.user, workspace=self.workspace)
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)

    def test_returns_zero_on_exception(self):
        # Simulate an unexpected exception inside the processor
        request = self.factory.get("/")
        request.user = self.user
        request.workspace = "not-a-workspace"  # Will cause attribute errors inside
        context = onboarding_context(request)
        self.assertEqual(context["onboarding_pending_count"], 0)


class TestDefaultWorkspaceContextProcessor(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.workspace = WorkspaceFactory()
        self.user = UserFactory()
        MembershipFactory(workspace=self.workspace, user=self.user, role=ROLE_MEMBER)

    def test_returns_workspace_when_request_has_workspace_attribute(self):
        request = self.factory.get("/")
        request.workspace = self.workspace
        context = default_workspace(request)
        self.assertEqual(context.get("default_workspace"), self.workspace)

    def test_falls_back_to_user_workspace_when_no_request_workspace(self):
        request = self.factory.get("/")
        request.user = self.user
        context = default_workspace(request)
        self.assertEqual(context.get("default_workspace"), self.workspace)

    def test_returns_empty_dict_for_unauthenticated_user_without_workspace(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()
        context = default_workspace(request)
        self.assertNotIn("default_workspace", context)

    def test_returns_empty_dict_when_user_has_no_workspaces(self):
        user_without_workspaces = UserFactory()
        request = self.factory.get("/")
        request.user = user_without_workspaces
        context = default_workspace(request)
        self.assertNotIn("default_workspace", context)

    def test_returns_empty_dict_when_no_user_attribute(self):
        request = self.factory.get("/")
        context = default_workspace(request)
        self.assertNotIn("default_workspace", context)
