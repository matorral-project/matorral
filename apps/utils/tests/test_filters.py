from django.test import TestCase

from apps.utils.filters import (
    build_filter_section,
    count_active_filters,
    get_status_filter_label,
    parse_multi_filter,
    parse_status_filter,
)


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


class CountActiveFiltersTest(TestCase):
    """Tests for count_active_filters utility function."""

    def test_empty_dict_returns_zero(self):
        self.assertEqual(count_active_filters({}), 0)

    def test_all_empty_values_returns_zero(self):
        self.assertEqual(count_active_filters({"status": "", "assignee": ""}), 0)

    def test_counts_non_empty_values(self):
        self.assertEqual(count_active_filters({"status": "active", "assignee": ""}), 1)

    def test_counts_all_when_all_filled(self):
        self.assertEqual(count_active_filters({"status": "active", "assignee": "user1"}), 2)


class ParseMultiFilterTest(TestCase):
    """Tests for parse_multi_filter utility function."""

    CHOICES = [("story", "Story"), ("bug", "Bug"), ("chore", "Chore")]

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_multi_filter("", self.CHOICES), [])

    def test_valid_values_are_returned(self):
        self.assertEqual(parse_multi_filter("story,bug", self.CHOICES), ["story", "bug"])

    def test_invalid_values_are_filtered_out(self):
        self.assertEqual(parse_multi_filter("story,unknown", self.CHOICES), ["story"])

    def test_whitespace_is_stripped(self):
        self.assertEqual(parse_multi_filter(" story , bug ", self.CHOICES), ["story", "bug"])


class BuildFilterSectionTest(TestCase):
    """Tests for build_filter_section utility function."""

    CHOICES = [("active", "Active"), ("draft", "Draft")]

    def test_basic_section_structure(self):
        section = build_filter_section("status", "Status", "multi_select", self.CHOICES, "active")
        self.assertEqual(section["name"], "status")
        self.assertEqual(section["label"], "Status")
        self.assertEqual(section["type"], "multi_select")
        self.assertEqual(section["choices"], self.CHOICES)
        self.assertEqual(section["current_value"], "active")

    def test_none_current_value_defaults_to_empty_string(self):
        section = build_filter_section("status", "Status", "multi_select", self.CHOICES, None)
        self.assertEqual(section["current_value"], "")

    def test_single_select_with_empty_label(self):
        section = build_filter_section("status", "Status", "single_select", self.CHOICES, "", empty_label="All")
        self.assertEqual(section["empty_label"], "All")

    def test_single_select_without_empty_label_omits_key(self):
        section = build_filter_section("status", "Status", "single_select", self.CHOICES, "")
        self.assertNotIn("empty_label", section)

    def test_multi_select_ignores_empty_label(self):
        section = build_filter_section("status", "Status", "multi_select", self.CHOICES, "", empty_label="All")
        self.assertNotIn("empty_label", section)
