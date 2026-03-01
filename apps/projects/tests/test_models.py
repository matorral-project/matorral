from django.test import TestCase

from apps.issues.factories import BugFactory, ChoreFactory, EpicFactory, StoryFactory
from apps.projects.factories import ProjectFactory
from apps.projects.models import Project
from apps.sprints.factories import SprintFactory
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


class ProjectMoveTest(TestCase):
    """Tests for Project.move(target_workspace)."""

    @classmethod
    def setUpTestData(cls):
        cls.source_workspace = WorkspaceFactory()
        cls.target_workspace = WorkspaceFactory()

    def test_move_changes_workspace(self):
        """Project.workspace is updated to the target workspace after move."""
        project = ProjectFactory(workspace=self.source_workspace, key="ALPHA")

        project.move(self.target_workspace)

        project.refresh_from_db()
        self.assertEqual(project.workspace, self.target_workspace)

    def test_move_preserves_key_when_no_conflict(self):
        """Key is unchanged when no project in the target workspace has that key."""
        project = ProjectFactory(workspace=self.source_workspace, key="ALPHA")

        project.move(self.target_workspace)

        project.refresh_from_db()
        self.assertEqual(project.key, "ALPHA")

    def test_move_generates_new_key_on_conflict(self):
        """When the key is already taken in the target workspace, a new unique key is generated."""
        ProjectFactory(workspace=self.target_workspace, key="ALPHA")
        project = ProjectFactory(workspace=self.source_workspace, key="ALPHA")

        project.move(self.target_workspace)

        project.refresh_from_db()
        self.assertNotEqual(project.key, "ALPHA")
        self.assertEqual(project.workspace, self.target_workspace)
        # Only one project with key ALPHA should remain in the target workspace
        self.assertEqual(Project.objects.filter(workspace=self.target_workspace, key="ALPHA").count(), 1)

    def test_move_updates_issue_keys_when_project_key_changes(self):
        """When project key changes, all issue keys are updated via SQL REPLACE."""
        ProjectFactory(workspace=self.target_workspace, key="ALPHA")
        project = ProjectFactory(workspace=self.source_workspace, key="ALPHA")
        epic = EpicFactory(project=project)
        story = StoryFactory(project=project)

        old_epic_key = epic.key
        old_story_key = story.key
        self.assertTrue(old_epic_key.startswith("ALPHA-"))
        self.assertTrue(old_story_key.startswith("ALPHA-"))

        project.move(self.target_workspace)
        new_key = project.key

        epic.refresh_from_db()
        story.refresh_from_db()
        self.assertTrue(epic.key.startswith(f"{new_key}-"))
        self.assertTrue(story.key.startswith(f"{new_key}-"))
        self.assertFalse(epic.key.startswith("ALPHA-"))
        self.assertFalse(story.key.startswith("ALPHA-"))

    def test_move_does_not_update_issue_keys_when_key_unchanged(self):
        """Issue keys are not modified when the project key does not change."""
        project = ProjectFactory(workspace=self.source_workspace, key="BETA")
        epic = EpicFactory(project=project)
        original_key = epic.key

        project.move(self.target_workspace)

        epic.refresh_from_db()
        self.assertEqual(epic.key, original_key)

    def test_move_clears_sprint_from_stories(self):
        """Stories lose their sprint assignment when the project is moved."""
        sprint = SprintFactory(workspace=self.source_workspace)
        project = ProjectFactory(workspace=self.source_workspace, key="GAMMA")
        story = StoryFactory(project=project, sprint=sprint)

        project.move(self.target_workspace)

        story.refresh_from_db()
        self.assertIsNone(story.sprint)

    def test_move_clears_sprint_from_bugs(self):
        """Bugs lose their sprint assignment when the project is moved."""
        sprint = SprintFactory(workspace=self.source_workspace)
        project = ProjectFactory(workspace=self.source_workspace, key="DELTA")
        bug = BugFactory(project=project, sprint=sprint)

        project.move(self.target_workspace)

        bug.refresh_from_db()
        self.assertIsNone(bug.sprint)

    def test_move_clears_sprint_from_chores(self):
        """Chores lose their sprint assignment when the project is moved."""
        sprint = SprintFactory(workspace=self.source_workspace)
        project = ProjectFactory(workspace=self.source_workspace, key="ECHO")
        chore = ChoreFactory(project=project, sprint=sprint)

        project.move(self.target_workspace)

        chore.refresh_from_db()
        self.assertIsNone(chore.sprint)
