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
)
from apps.projects.factories import ProjectFactory

import factory


class MilestoneFactory(factory.django.DjangoModelFactory):
    """Factory for creating project-scoped Milestone instances (treebeard root nodes)."""

    class Meta:
        model = Milestone

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Milestone {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM
    assignee = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to use treebeard's add_root method (milestones are always root-level)."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        return BaseIssue.add_root(instance=obj)


class EpicFactory(factory.django.DjangoModelFactory):
    """Factory for creating Epic instances."""

    class Meta:
        model = Epic

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Epic {n}")
    key = ""
    description = ""
    status = IssueStatus.DRAFT

    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to use treebeard's add_root or add_child method."""
        obj = model_class(**kwargs)
        obj.key = obj.key or obj._generate_unique_key()
        if parent:
            return parent.add_child(instance=obj)
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

    project = factory.SubFactory(ProjectFactory)
    title = factory.Sequence(lambda n: f"Subtask {n}")
    status = IssueStatus.DRAFT
    priority = IssuePriority.MEDIUM

    @classmethod
    def _create(cls, model_class, *args, parent=None, **kwargs):
        """Override to use treebeard's add_child method. Requires a parent."""
        if parent is None:
            raise ValueError("SubtaskFactory requires a 'parent' argument (a work item instance)")
        kwargs["project"] = parent.project
        obj = model_class(**kwargs)
        obj.key = obj._generate_unique_key()
        return parent.add_child(instance=obj)
