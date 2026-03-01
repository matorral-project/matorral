from django.test import RequestFactory, TestCase, override_settings

from matorral.context_processors import base_context, google_analytics_id


class TestBaseContext(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_contains_required_keys(self):
        request = self.factory.get("/")
        ctx = base_context(request)
        for key in ("site", "server_url", "page_url", "site_description", "site_keywords", "is_debug", "env_badge"):
            self.assertIn(key, ctx)

    @override_settings(ENVIRONMENT="local")
    def test_env_badge_for_local(self):
        request = self.factory.get("/")
        ctx = base_context(request)
        self.assertEqual(ctx["env_badge"], "local")

    @override_settings(ENVIRONMENT="production")
    def test_env_badge_for_production(self):
        request = self.factory.get("/")
        ctx = base_context(request)
        self.assertEqual(ctx["env_badge"], "beta")

    @override_settings(ENVIRONMENT="staging")
    def test_env_badge_for_other_env(self):
        request = self.factory.get("/")
        ctx = base_context(request)
        self.assertEqual(ctx["env_badge"], "demo")


class TestGoogleAnalyticsContext(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(GOOGLE_ANALYTICS_ID="UA-12345-1")
    def test_analytics_id_present_when_set(self):
        request = self.factory.get("/")
        ctx = google_analytics_id(request)
        self.assertIn("GOOGLE_ANALYTICS_ID", ctx)
        self.assertEqual(ctx["GOOGLE_ANALYTICS_ID"], "UA-12345-1")

    @override_settings(GOOGLE_ANALYTICS_ID="")
    def test_analytics_id_absent_when_not_set(self):
        request = self.factory.get("/")
        ctx = google_analytics_id(request)
        self.assertEqual(ctx, {})
