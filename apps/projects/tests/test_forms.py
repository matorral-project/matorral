from django.test import TestCase

from apps.projects.forms import ProjectForm
from apps.projects.models import Project, ProjectStatus
from apps.workspaces.factories import WorkspaceFactory


class ProjectFormKeyValidationTest(TestCase):
    """Tests for project key validation in ProjectForm."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def test_key_with_numbers_is_invalid(self):
        """Keys containing numbers are rejected."""
        form = ProjectForm(
            data={"name": "Test", "key": "PRJ1", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)
        self.assertIn("only letters", form.errors["key"][0])

    def test_key_with_dash_is_invalid(self):
        """Keys containing dashes are rejected."""
        form = ProjectForm(
            data={"name": "Test", "key": "PRJ-1", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)
        self.assertIn("only letters", form.errors["key"][0])

    def test_key_with_underscore_is_invalid(self):
        """Keys containing underscores are rejected."""
        form = ProjectForm(
            data={"name": "Test", "key": "PRJ_A", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)
        self.assertIn("only letters", form.errors["key"][0])

    def test_key_too_long_is_invalid(self):
        """Keys longer than 6 characters are rejected."""
        form = ProjectForm(
            data={"name": "Test", "key": "TOOLONG", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)
        self.assertIn("at most 6 characters", form.errors["key"][0])

    def test_key_with_only_letters_is_valid(self):
        """Keys containing only ASCII letters are accepted."""
        form = ProjectForm(
            data={"name": "Test", "key": "PROJ", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertTrue(form.is_valid())

    def test_key_with_lowercase_letters_is_valid(self):
        """Lowercase keys are accepted (will be normalized to uppercase)."""
        form = ProjectForm(
            data={"name": "Test", "key": "proj", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertTrue(form.is_valid())

    def test_key_with_six_characters_is_valid(self):
        """Keys with exactly 6 characters are accepted."""
        form = ProjectForm(
            data={"name": "Test", "key": "ABCDEF", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertTrue(form.is_valid())

    def test_empty_key_is_valid(self):
        """Empty key is accepted (will be auto-generated)."""
        form = ProjectForm(
            data={"name": "Test", "key": "", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertTrue(form.is_valid())

    def test_duplicate_key_is_invalid(self):
        """Duplicate keys within the same workspace are rejected."""
        Project.objects.create(workspace=self.workspace, name="Existing", key="EXIST")

        form = ProjectForm(
            data={"name": "Test", "key": "EXIST", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("key", form.errors)
        self.assertIn("already exists", form.errors["key"][0])

    def test_same_key_on_update_is_valid(self):
        """Keeping the same key when updating is allowed."""
        project = Project.objects.create(workspace=self.workspace, name="Test", key="EXIST")

        form = ProjectForm(
            data={"name": "Test", "key": "EXIST", "status": ProjectStatus.DRAFT},
            workspace=self.workspace,
            instance=project,
        )

        self.assertTrue(form.is_valid())
