from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from apps.issues.factories import BugFactory, StoryFactory
from apps.issues.models import Bug, Story
from apps.projects.factories import ProjectFactory
from apps.projects.models import ProjectStatus
from apps.sprints.factories import SprintFactory
from apps.users.factories import CustomUserFactory
from apps.utils.audit import bulk_create_audit_logs

from auditlog.models import LogEntry


class BulkCreateAuditLogsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUserFactory()
        cls.project = ProjectFactory()

    def test_creates_log_entry_for_each_changed_object(self):
        p1 = ProjectFactory(status=ProjectStatus.DRAFT)
        p2 = ProjectFactory(status=ProjectStatus.DRAFT)
        old_values = {p1.pk: "Draft", p2.pk: "Draft"}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([p1, p2], "status", old_values, "Active", actor=self.user)

        entries = LogEntry.objects.all()
        self.assertEqual(entries.count(), 2)
        for entry in entries:
            self.assertEqual(entry.action, LogEntry.Action.UPDATE)
            self.assertEqual(entry.changes, {"status": ["Draft", "Active"]})
            self.assertEqual(entry.actor, self.user)

    def test_skips_objects_where_old_equals_new(self):
        p1 = ProjectFactory(status=ProjectStatus.DRAFT)
        p2 = ProjectFactory(status=ProjectStatus.ACTIVE)
        old_values = {p1.pk: "Draft", p2.pk: "Active"}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([p1, p2], "status", old_values, "Active", actor=self.user)

        entries = LogEntry.objects.all()
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().object_id, p1.pk)

    def test_empty_objects_list_creates_nothing(self):
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([], "status", {}, "Active", actor=self.user)

        self.assertEqual(LogEntry.objects.count(), 0)

    def test_polymorphic_models_get_correct_content_type(self):
        story = StoryFactory(project=self.project)
        bug = BugFactory(project=self.project)
        old_values = {story.pk: "Draft", bug.pk: "Draft"}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([story, bug], "status", old_values, "Active", actor=self.user)

        story_ct = ContentType.objects.get_for_model(Story)
        bug_ct = ContentType.objects.get_for_model(Bug)

        story_entry = LogEntry.objects.get(object_id=story.pk)
        bug_entry = LogEntry.objects.get(object_id=bug.pk)

        self.assertEqual(story_entry.content_type, story_ct)
        self.assertEqual(bug_entry.content_type, bug_ct)

    def test_object_repr_uses_str(self):
        p = ProjectFactory(name="My Project")
        old_values = {p.pk: "Draft"}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([p], "status", old_values, "Active", actor=self.user)

        entry = LogEntry.objects.first()
        self.assertEqual(entry.object_repr, "My Project")

    def test_none_values_stored_correctly(self):
        sprint = SprintFactory()
        story = StoryFactory(project=self.project, sprint=sprint)
        old_values = {story.pk: str(sprint)}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([story], "sprint", old_values, None, actor=self.user)

        entry = LogEntry.objects.first()
        self.assertEqual(entry.changes, {"sprint": [str(sprint), None]})

    def test_works_without_actor(self):
        p = ProjectFactory(status=ProjectStatus.DRAFT)
        old_values = {p.pk: "Draft"}
        LogEntry.objects.all().delete()

        bulk_create_audit_logs([p], "status", old_values, "Active")

        entry = LogEntry.objects.first()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.changes, {"status": ["Draft", "Active"]})
