from django.test import TestCase
from django.urls import reverse

from matorral.stories.factories import StoryFactory
from matorral.workspaces.factories import WorkspaceFactory


class StoryViewsTest(TestCase):
    def setUp(self):
        self.workspace = WorkspaceFactory.create()
        self.story = StoryFactory.create(workspace=self.workspace)

    def test_list(self):
        response = self.client.get(reverse("stories:story-list", args=[self.workspace.slug]))
        self.assertEqual(response.status_code, 302)

    def test_detail(self):
        response = self.client.get(self.story.get_absolute_url())
        self.assertEqual(response.status_code, 302)
