from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    def items(self):
        return [
            ("landing_pages:home", 1.0, "weekly"),
            ("landing_pages:terms", 0.3, "yearly"),
            ("landing_pages:privacy", 0.3, "yearly"),
        ]

    def location(self, item):
        url_name, priority, changefreq = item
        return reverse(url_name)

    def priority(self, item):
        url_name, priority, changefreq = item
        return priority

    def changefreq(self, item):
        url_name, priority, changefreq = item
        return changefreq
