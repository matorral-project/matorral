from django.test import TestCase

from apps.utils.progress import build_progress_dict, calculate_progress


class ProgressUtilsTest(TestCase):
    """Test the progress utility functions."""

    def test_build_progress_dict_with_zero_total(self):
        """Test build_progress_dict returns None when total is 0."""
        result = build_progress_dict(0, 0, 0, 0)
        self.assertIsNone(result)

    def test_build_progress_dict_normal_case(self):
        """Test build_progress_dict with normal values."""
        result = build_progress_dict(30, 20, 50, 100)
        expected = {
            "done_pct": 30,
            "in_progress_pct": 20,
            "todo_pct": 50,
            "done_weight": 30,
            "in_progress_weight": 20,
            "todo_weight": 50,
            "total_weight": 100,
        }
        self.assertEqual(result, expected)

    def test_build_progress_dict_rounding(self):
        """Test build_progress_dict handles rounding correctly."""
        # Case where rounding might cause issues
        result = build_progress_dict(33, 33, 34, 100)
        expected = {
            "done_pct": 33,
            "in_progress_pct": 33,
            "todo_pct": 34,
            "done_weight": 33,
            "in_progress_weight": 33,
            "todo_weight": 34,
            "total_weight": 100,
        }
        self.assertEqual(result, expected)

    def test_calculate_progress_with_empty_issues(self):
        """Test calculate_progress returns None with empty issues."""
        result = calculate_progress([])
        self.assertIsNone(result)
