from django.test import TestCase

from apps.sprints.forms import SprintDetailInlineEditForm
from apps.sprints.models import SprintStatus


class SprintDetailInlineEditFormCleanGoalTest(TestCase):
    """Tests for SprintDetailInlineEditForm.clean_goal()."""

    def _make_form(self, goal):
        data = {
            "name": "Sprint 1",
            "status": SprintStatus.PLANNING,
            "goal": goal,
        }
        return SprintDetailInlineEditForm(data=data)

    def test_clean_goal_strips_whitespace(self):
        """Goal value should be stripped of leading and trailing whitespace."""
        form = self._make_form("  some goal  ")

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["goal"], "some goal")

    def test_clean_goal_empty_string_returns_empty(self):
        """Empty string goal returns empty string."""
        form = self._make_form("")

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["goal"], "")
