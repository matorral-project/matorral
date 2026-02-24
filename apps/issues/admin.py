from django.contrib import admin

from apps.issues.models import BaseIssue, Bug, Chore, Epic, Milestone, Story

from polymorphic.admin import PolymorphicChildModelAdmin, PolymorphicChildModelFilter, PolymorphicParentModelAdmin


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    """Admin for project-scoped Milestones."""

    list_display = [
        "key",
        "title",
        "project",
        "status",
        "priority",
        "owner",
        "due_date",
    ]
    list_filter = ["status", "priority", "project"]
    search_fields = ["key", "title"]
    readonly_fields = ["key", "created_at", "updated_at"]
    raw_id_fields = ["project", "owner"]


class BaseIssueChildAdmin(PolymorphicChildModelAdmin):
    """Base admin for all issue child models."""

    base_model = BaseIssue
    readonly_fields = ["key", "path", "depth", "created_at", "updated_at"]


@admin.register(Epic)
class EpicAdmin(BaseIssueChildAdmin):
    base_model = Epic
    list_display = ["key", "title", "project", "status", "milestone", "due_date"]
    list_filter = ["status", "project", "milestone"]
    search_fields = ["key", "title"]
    raw_id_fields = ["milestone"]


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


@admin.register(BaseIssue)
class BaseIssueParentAdmin(PolymorphicParentModelAdmin):
    """Parent admin for browsing all issue types."""

    base_model = BaseIssue
    child_models = (Epic, Story, Bug, Chore)
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
