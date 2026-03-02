from django.test import TestCase

from apps.workspaces.factories import WorkspaceFactory
from apps.workspaces.slugs import get_next_unique_workspace_slug


class TestGetNextUniqueWorkspaceSlug(TestCase):
    def test_returns_incremented_slug_when_base_slug_exists(self):
        WorkspaceFactory(slug="acme")

        slug = get_next_unique_workspace_slug("Acme")

        self.assertEqual(slug, "acme-2")
