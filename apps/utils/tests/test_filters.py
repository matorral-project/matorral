from django.test import TestCase

from apps.utils.filters import get_status_filter_label, parse_status_filter


class ParseStatusFilterTest(TestCase):
    """Tests for parse_status_filter utility function."""

    CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    def test_empty_string_returns_empty_list(self):
        result = parse_status_filter("", self.CHOICES)
        self.assertEqual(result, [])

    def test_single_valid_value(self):
        result = parse_status_filter("draft", self.CHOICES)
        self.assertEqual(result, ["draft"])

    def test_multiple_valid_values(self):
        result = parse_status_filter("draft,active", self.CHOICES)
        self.assertEqual(result, ["draft", "active"])

    def test_all_valid_values(self):
        result = parse_status_filter("draft,active,completed,archived", self.CHOICES)
        self.assertEqual(result, ["draft", "active", "completed", "archived"])

    def test_invalid_values_are_filtered_out(self):
        result = parse_status_filter("draft,invalid,active,bogus", self.CHOICES)
        self.assertEqual(result, ["draft", "active"])

    def test_all_invalid_values_returns_empty_list(self):
        result = parse_status_filter("invalid,bogus,nonexistent", self.CHOICES)
        self.assertEqual(result, [])

    def test_whitespace_handling(self):
        result = parse_status_filter(" draft , active , completed ", self.CHOICES)
        self.assertEqual(result, ["draft", "active", "completed"])

    def test_empty_segments_are_ignored(self):
        result = parse_status_filter("draft,,active,", self.CHOICES)
        self.assertEqual(result, ["draft", "active"])


class GetStatusFilterLabelTest(TestCase):
    """Tests for get_status_filter_label utility function."""

    CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    ]

    def test_empty_string_returns_empty_label(self):
        result = get_status_filter_label("", self.CHOICES)
        self.assertEqual(result, "")

    def test_single_status_returns_label(self):
        result = get_status_filter_label("draft", self.CHOICES)
        self.assertEqual(result, "Draft")

    def test_single_status_active(self):
        result = get_status_filter_label("active", self.CHOICES)
        self.assertEqual(result, "Active")

    def test_two_statuses_returns_count_label(self):
        result = get_status_filter_label("draft,active", self.CHOICES)
        self.assertIn("2", str(result))

    def test_three_statuses_returns_count_label(self):
        result = get_status_filter_label("draft,active,completed", self.CHOICES)
        self.assertIn("3", str(result))

    def test_invalid_value_returns_empty_label(self):
        result = get_status_filter_label("invalid", self.CHOICES)
        self.assertEqual(result, "")

    def test_mixed_valid_invalid_uses_valid_count(self):
        result = get_status_filter_label("draft,invalid,active", self.CHOICES)
        self.assertIn("2", str(result))
