from django.test import TestCase

from apps.projects.models import Project
from apps.workspaces.factories import WorkspaceFactory


class ProjectKeyAutoGenerationTest(TestCase):
    """Tests for automatic key generation from project names."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def test_key_auto_generated_when_blank(self):
        """Key is auto-generated if not provided."""
        project = Project.objects.create(workspace=self.workspace, name="Test Project")

        self.assertNotEqual("", project.key)
        # Multi-word name uses initials
        self.assertEqual("TP", project.key)

    def test_key_generated_from_single_word_name(self):
        """Single word names use first 3 letters: 'Marketing' -> 'MAR'."""
        project = Project.objects.create(workspace=self.workspace, name="Marketing")

        self.assertEqual("MAR", project.key)

    def test_key_generated_from_two_word_name(self):
        """Two word names use initials: 'New Product' -> 'NP'."""
        project = Project.objects.create(workspace=self.workspace, name="New Product")

        self.assertEqual("NP", project.key)

    def test_key_generated_from_multi_word_name(self):
        """Multi-word names use initials: 'Super Cool Project' -> 'SCP'."""
        project = Project.objects.create(workspace=self.workspace, name="Super Cool Project")

        self.assertEqual("SCP", project.key)

    def test_key_generated_from_name_with_special_chars(self):
        """Special characters are filtered out: 'Test & Dev' -> 'TD'."""
        project = Project.objects.create(workspace=self.workspace, name="Test & Dev")

        # Note: "&" is filtered out, only ASCII letters are used
        self.assertEqual("TD", project.key)

    def test_key_generated_from_name_with_parentheses(self):
        """Parentheses are filtered out: 'Test Project (Copy)' -> 'TPC'."""
        project = Project.objects.create(workspace=self.workspace, name="Test Project (Copy)")

        # Parentheses are stripped, "Copy" starts with "C"
        self.assertEqual("TPC", project.key)

    def test_key_length_increases_when_taken(self):
        """When 3-letter key is taken, tries 4 letters, then 5, then 6."""
        # First project gets 3-letter key
        project1 = Project.objects.create(workspace=self.workspace, name="Marketing")
        self.assertEqual("MAR", project1.key)

        # Second project with same base gets 4-letter key
        project2 = Project.objects.create(workspace=self.workspace, name="Market Research")
        # Multi-word, so uses initials "MR"
        self.assertEqual("MR", project2.key)

        # Third project: "Marketplace" - "MAR" is taken, so gets "MARK"
        project3 = Project.objects.create(workspace=self.workspace, name="Marketplace")
        self.assertEqual("MARK", project3.key)

        # Fourth project: "Marketable" - "MAR" and "MARK" taken, gets "MARKE"
        project4 = Project.objects.create(workspace=self.workspace, name="Marketable")
        self.assertEqual("MARKE", project4.key)

    def test_key_uses_letter_suffix_when_all_lengths_exhausted(self):
        """When all lengths 3-6 are taken, appends a letter suffix."""
        # Create projects that exhaust MAR, MARK, MARKE, MARKET
        Project.objects.create(workspace=self.workspace, name="M1", key="MAR")
        Project.objects.create(workspace=self.workspace, name="M2", key="MARK")
        Project.objects.create(workspace=self.workspace, name="M3", key="MARKE")
        Project.objects.create(workspace=self.workspace, name="M4", key="MARKET")

        # Next project should get a suffix (5 chars + 1 letter = 6 chars max)
        project = Project.objects.create(workspace=self.workspace, name="Marketing")
        self.assertEqual("MARKEA", project.key)

    def test_multi_word_falls_back_to_length_when_initials_taken(self):
        """Multi-word names fall back to length-based keys when initials are taken."""
        # Take the initials "TP"
        Project.objects.create(workspace=self.workspace, name="Test Project")

        # Next project with same initials should use full concatenated words
        project2 = Project.objects.create(workspace=self.workspace, name="Test Plan")
        # "TESTPLAN" -> tries TES (3), TEST (4), etc.
        self.assertEqual("TES", project2.key)


class ProjectKeyNormalizationTest(TestCase):
    """Tests for key normalization behavior."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = WorkspaceFactory()

    def test_key_normalized_to_uppercase(self):
        """Lowercase keys are converted to uppercase: 'proj' -> 'PROJ'."""
        project = Project.objects.create(workspace=self.workspace, name="Test", key="proj")

        self.assertEqual("PROJ", project.key)

    def test_key_whitespace_stripped(self):
        """Whitespace is stripped from keys: ' PROJ ' -> 'PROJ'."""
        project = Project.objects.create(workspace=self.workspace, name="Test", key=" PROJ ")

        self.assertEqual("PROJ", project.key)

    def test_explicit_key_preserved(self):
        """Provided key is used (after normalization)."""
        project = Project.objects.create(workspace=self.workspace, name="Marketing Campaign", key="custom")

        self.assertEqual("CUSTOM", project.key)
