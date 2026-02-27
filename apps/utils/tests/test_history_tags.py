from unittest.mock import MagicMock

from django.test import TestCase

from apps.utils.templatetags.history_tags import (
    format_history_entry,
    history_action_icon,
    history_action_label,
)

from auditlog.models import LogEntry


def make_entry(action, changes=None):
    entry = MagicMock(spec=LogEntry)
    entry.action = action
    entry.changes = changes or {}
    return entry


class FormatHistoryEntryTest(TestCase):
    """Tests for the format_history_entry template tag."""

    def test_create_with_model_name(self):
        entry = make_entry(LogEntry.Action.CREATE)
        result = format_history_entry(entry, "story")
        self.assertEqual(result, "created this story")

    def test_create_without_model_name(self):
        entry = make_entry(LogEntry.Action.CREATE)
        result = format_history_entry(entry)
        self.assertEqual(result, "created this item")

    def test_delete_with_model_name(self):
        entry = make_entry(LogEntry.Action.DELETE)
        result = format_history_entry(entry, "epic")
        self.assertEqual(result, "deleted this epic")

    def test_delete_without_model_name(self):
        entry = make_entry(LogEntry.Action.DELETE)
        result = format_history_entry(entry)
        self.assertEqual(result, "deleted this item")

    def test_update_text_field_shows_edited(self):
        entry = make_entry(LogEntry.Action.UPDATE, {"description": ["old text", "new text"]})
        result = format_history_entry(entry)
        self.assertEqual(result, "edited description")

    def test_update_single_field_shows_set(self):
        entry = make_entry(LogEntry.Action.UPDATE, {"status": ["Draft", "Active"]})
        result = format_history_entry(entry)
        self.assertEqual(result, "set status to Active")

    def test_update_two_fields_joined_with_and(self):
        entry = make_entry(LogEntry.Action.UPDATE, {"status": ["Draft", "Active"], "priority": [None, "High"]})
        result = format_history_entry(entry)
        self.assertIn(" and ", result)
        self.assertIn("Active", result)
        self.assertIn("High", result)

    def test_update_three_fields_uses_commas(self):
        entry = make_entry(
            LogEntry.Action.UPDATE,
            {"status": ["Draft", "Active"], "priority": [None, "High"], "title": ["old", "new"]},
        )
        result = format_history_entry(entry)
        self.assertIn(", and ", result)

    def test_update_with_no_changes_returns_made_changes(self):
        entry = make_entry(LogEntry.Action.UPDATE, {})
        result = format_history_entry(entry)
        self.assertEqual(result, "made changes")

    def test_update_none_new_value_shows_empty(self):
        entry = make_entry(LogEntry.Action.UPDATE, {"assignee": ["Alice", None]})
        result = format_history_entry(entry)
        self.assertIn("empty", result)

    def test_access_with_model_name(self):
        entry = make_entry(LogEntry.Action.ACCESS)
        result = format_history_entry(entry, "story")
        self.assertEqual(result, "viewed this story")

    def test_access_without_model_name(self):
        entry = make_entry(LogEntry.Action.ACCESS)
        result = format_history_entry(entry)
        self.assertEqual(result, "viewed this item")


class HistoryActionIconTest(TestCase):
    """Tests for the history_action_icon template tag."""

    def test_create_returns_plus_circle(self):
        entry = make_entry(LogEntry.Action.CREATE)
        self.assertIn("fa-plus-circle", history_action_icon(entry))

    def test_update_returns_pencil(self):
        entry = make_entry(LogEntry.Action.UPDATE)
        self.assertIn("fa-pencil", history_action_icon(entry))

    def test_delete_returns_trash(self):
        entry = make_entry(LogEntry.Action.DELETE)
        self.assertIn("fa-trash", history_action_icon(entry))

    def test_access_returns_eye(self):
        entry = make_entry(LogEntry.Action.ACCESS)
        self.assertIn("fa-eye", history_action_icon(entry))


class HistoryActionLabelTest(TestCase):
    """Tests for the history_action_label template tag."""

    def test_create_label(self):
        entry = make_entry(LogEntry.Action.CREATE)
        self.assertEqual(history_action_label(entry), "Created")

    def test_update_label(self):
        entry = make_entry(LogEntry.Action.UPDATE)
        self.assertEqual(history_action_label(entry), "Updated")

    def test_delete_label(self):
        entry = make_entry(LogEntry.Action.DELETE)
        self.assertEqual(history_action_label(entry), "Deleted")

    def test_access_label(self):
        entry = make_entry(LogEntry.Action.ACCESS)
        self.assertEqual(history_action_label(entry), "Accessed")
