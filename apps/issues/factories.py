from apps.issues.models import (
    BaseIssue,
    Bug,
    BugSeverity,
    Chore,
    Epic,
    IssuePriority,
    IssueStatus,
    Milestone,
    Story,
    Subtask,
    SubtaskStatus,
)
from apps.issues.utils import get_cached_content_type
from apps.projects.factories import ProjectFactory

import factory


class MilestoneFactory(factory.django.DjangoModelFactory):
    """Factory for creating project-scoped Milestone instances."""

    class Meta:
        model = Milestone

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Milestone {n}")
    key = ""  # Let the model auto-generate
    description = ""
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM
    owner = None


class EpicFactory(factory.django.DjangoModelFactory):
    """Factory for creating Epic instances."""

    class Meta:
        model = Epic

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Epic {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT
    milestone = None  # Optional FK to workspace-scoped Milestone

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use treebeard's add_root method (epics are always root-level)."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        return BaseIssue.add_root(instance=obj)


class StoryFactory(factory.django.DjangoModelFactory):
    """Factory for creating Story instances."""

    class Meta:
        model = Story

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Story {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM
    estimated_points = None

    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to use treebeard's add_root or add_child method."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        if parent:
            return parent.add_child(instance=obj)
        return BaseIssue.add_root(instance=obj)


class BugFactory(factory.django.DjangoModelFactory):
    """Factory for creating Bug instances."""

    class Meta:
        model = Bug

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Bug {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM
    estimated_points = None
    severity = BugSeverity.MINOR

    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to use treebeard's add_root or add_child method."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        if parent:
            return parent.add_child(instance=obj)
        return BaseIssue.add_root(instance=obj)


class ChoreFactory(factory.django.DjangoModelFactory):
    """Factory for creating Chore instances."""

    class Meta:
        model = Chore

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Chore {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM
    estimated_points = None

    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to use treebeard's add_root or add_child method."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        if parent:
            return parent.add_child(instance=obj)
        return BaseIssue.add_root(instance=obj)


class SubtaskFactory(factory.django.DjangoModelFactory):
    """Factory for creating Subtask instances."""

    class Meta:
        model = Subtask

    title = factory.Sequence(lambda n: f"Subtask {n}")
    status = SubtaskStatus.TODO
    position = factory.Sequence(lambda n: n)

    # The parent must be provided and will set content_type and object_id
    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to set GenericForeignKey fields from parent."""
        if parent is None:
            raise ValueError("SubtaskFactory requires a 'parent' argument (a work item instance)")

        content_type = get_cached_content_type(type(parent))
        kwargs["content_type"] = content_type
        kwargs["object_id"] = parent.pk

        return super()._create(model_class, *args, **kwargs)
