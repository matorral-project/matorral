from django.contrib import admin

from apps.issues.models import BaseIssue, Bug, Chore, Epic, Milestone, Story, Subtask

from polymorphic.admin import PolymorphicChildModelAdmin, PolymorphicChildModelFilter, PolymorphicParentModelAdmin


class BaseIssueChildAdmin(PolymorphicChildModelAdmin):
    """Base admin for all issue child models."""

    base_model = BaseIssue
    readonly_fields = ["key", "path", "depth", "created_at", "updated_at"]


@admin.register(Milestone)
class MilestoneAdmin(BaseIssueChildAdmin):
    """Admin for project-scoped Milestones."""

    base_model = Milestone
    list_display = ["key", "title", "project", "status", "priority", "assignee", "due_date"]
    list_filter = ["status", "priority", "project"]
    search_fields = ["key", "title"]


@admin.register(Epic)
class EpicAdmin(BaseIssueChildAdmin):
    base_model = Epic
    list_display = ["key", "title", "project", "status", "due_date"]
    list_filter = ["status", "project"]
    search_fields = ["key", "title"]


@admin.register(Story)
class StoryAdmin(BaseIssueChildAdmin):
    base_model = Story
    list_display = [
        "key",
        "title",
        "project",
        "status",
        "priority",
        "assignee",
        "estimated_points",
    ]
    list_filter = ["status", "priority", "project"]
    search_fields = ["key", "title"]


@admin.register(Bug)
class BugAdmin(BaseIssueChildAdmin):
    base_model = Bug
    list_display = [
        "key",
        "title",
        "project",
        "status",
        "priority",
        "severity",
        "assignee",
    ]
    list_filter = ["status", "priority", "severity", "project"]
    search_fields = ["key", "title"]


@admin.register(Chore)
class ChoreAdmin(BaseIssueChildAdmin):
    base_model = Chore
    list_display = ["key", "title", "project", "status", "priority", "assignee"]
    list_filter = ["status", "priority", "project"]
    search_fields = ["key", "title"]


@admin.register(Subtask)
class SubtaskAdmin(BaseIssueChildAdmin):
    base_model = Subtask
    list_display = ["key", "title", "project", "status", "priority"]
    list_filter = ["status", "priority", "project"]
    search_fields = ["key", "title"]


@admin.register(BaseIssue)
class BaseIssueParentAdmin(PolymorphicParentModelAdmin):
    """Parent admin for browsing all issue types."""

    base_model = BaseIssue
    child_models = (Milestone, Epic, Story, Bug, Chore, Subtask)
    list_display = [
        "key",
        "title",
        "project",
        "status",
        "get_issue_type_display",
        "created_at",
    ]
    list_filter = [PolymorphicChildModelFilter, "status", "project"]
    search_fields = ["key", "title"]
    readonly_fields = ["key", "path", "depth", "created_at", "updated_at"]
