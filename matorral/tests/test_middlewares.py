from django.contrib.sites.models import Site
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from matorral.middlewares import SiteDomainRedirectMiddleware

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}


@override_settings(DEBUG=False, CACHES=LOCMEM_CACHE)
class SiteDomainRedirectMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = lambda request: "ok"
        self.middleware = SiteDomainRedirectMiddleware(self.get_response)
        self.site = Site.objects.get_current()
        self.site.domain = "example.com"
        self.site.save()
        cache.clear()

    def test_redirects_mismatched_host(self):
        request = self.factory.get("/some/path/?q=1", HTTP_HOST="wrong.com")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://example.com/some/path/?q=1")

    def test_passes_through_matching_host(self):
        request = self.factory.get("/some/path/", HTTP_HOST="example.com")
        response = self.middleware(request)

        self.assertEqual(response, "ok")

    def test_strips_port_when_comparing(self):
        request = self.factory.get("/", HTTP_HOST="example.com:8000")
        response = self.middleware(request)

        self.assertEqual(response, "ok")

    def test_caches_site_domain(self):
        request = self.factory.get("/", HTTP_HOST="example.com")
        self.middleware(request)

        self.assertEqual(cache.get(SiteDomainRedirectMiddleware.CACHE_KEY), "example.com")

    def test_uses_cached_domain(self):
        cache.set(SiteDomainRedirectMiddleware.CACHE_KEY, "cached.com", 3600)
        request = self.factory.get("/path/", HTTP_HOST="other.com")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://cached.com/path/")

    def test_no_db_query_when_cached(self):
        cache.set(SiteDomainRedirectMiddleware.CACHE_KEY, "example.com", 3600)
        request = self.factory.get("/", HTTP_HOST="example.com")

        with self.assertNumQueries(0):
            self.middleware(request)

    def test_redirects_with_nonstandard_port(self):
        request = self.factory.get("/test/", HTTP_HOST="wrong.com:8443")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://example.com/test/")
