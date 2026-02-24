from django.contrib.auth import get_user_model
from django.db.models import Case, CharField, F, IntegerField, Value, When
from django.db.models.functions import Substr
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from apps.issues.forms import get_form_class_for_type
from apps.issues.models import BaseIssue, IssuePriority, IssueStatus
from apps.projects.models import Project
from apps.utils.filters import (
    build_filter_section,
    count_active_filters,
    get_status_filter_label,
    parse_multi_filter,
    parse_status_filter,
)
from apps.workspaces.models import Workspace

User = get_user_model()

# Issue type choices for filtering (milestones are workspace-scoped, not project issues)
ISSUE_TYPE_CHOICES = [
    ("epic", _("Epic")),
    ("story", _("Story")),
    ("bug", _("Bug")),
    ("chore", _("Chore")),
]

# Work item type choices (excludes epics) - used in epic detail where children are work items
WORK_ITEM_TYPE_CHOICES = [
    ("story", _("Story")),
    ("bug", _("Bug")),
    ("chore", _("Chore")),
]

# Model class mapping
ISSUE_TYPE_MODELS = {
    "epic": "Epic",
    "story": "Story",
    "bug": "Bug",
    "chore": "Chore",
}

# Group by choices for issue list
GROUP_BY_CHOICES = [
    ("epic", _("Epic")),
    ("status", _("Status")),
    ("priority", _("Priority")),
    ("assignee", _("Assignee")),
]

# Sort by choices for issue list (only shown when no grouping is active)
SORT_BY_CHOICES = [
    ("title_asc", _("Title A-Z")),
    ("title_desc", _("Title Z-A")),
    ("priority_desc", _("Priority High-Low")),
    ("priority_asc", _("Priority Low-High")),
    ("points_desc", _("Points High-Low")),
    ("points_asc", _("Points Low-High")),
]

# Sprint filter choices for backlog filtering
SPRINT_FILTER_CHOICES = [
    ("backlog", _("Backlog (not in sprint)")),
]


def get_status_order_annotation():
    """Create a Case/When annotation for ordering by status in definition order."""
    return Case(
        *[When(status=choice[0], then=Value(i)) for i, choice in enumerate(IssueStatus.choices)],
        default=Value(999),
        output_field=IntegerField(),
    )


def get_priority_order_annotation():
    """Create a Case/When annotation for ordering by priority (critical > high > medium > low)."""
    return Case(
        *[When(priority=choice[0], then=Value(i)) for i, choice in enumerate(IssuePriority.choices)],
        default=Value(999),
        output_field=IntegerField(),
    )


def get_assignee_order_annotation():
    """Create an annotation for ordering by assignee first name."""
    return F("assignee__first_name")


class IssueListContextMixin:
    """Shared filtering and context logic for issue list views."""

    def apply_issue_filters(
        self,
        queryset,
        type_filter: str,
        search_query: str,
        status_filter: str,
        assignee_filter: str,
        sprint_filter: str = "",
        priority_filter: str = "",
    ):
        """Apply type, search, status, assignee, sprint, and priority filters to an issue queryset."""
        from apps.issues.models import Bug, Chore, Epic, Story

        # Local model mapping (avoid circular imports)
        issue_type_models = {
            "epic": Epic,
            "story": Story,
            "bug": Bug,
            "chore": Chore,
        }

        # Apply sprint filter first (backlog filters to work items only)
        if sprint_filter == "backlog":
            queryset = queryset.backlog()

        # Apply type filter - supports single value or comma-separated multi-select
        type_values = parse_multi_filter(type_filter, ISSUE_TYPE_CHOICES)
        if len(type_values) == 1 and type_values[0] in issue_type_models:
            queryset = queryset.instance_of(issue_type_models[type_values[0]])
        elif len(type_values) > 1:
            model_classes = [issue_type_models[v] for v in type_values if v in issue_type_models]
            if model_classes:
                queryset = queryset.instance_of(*model_classes)

        # Apply search
        if search_query:
            queryset = queryset.search(search_query)

        # Apply status filter (supports comma-separated multi-select)
        status_values = parse_status_filter(status_filter, IssueStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)

        # Apply priority filter (supports comma-separated multi-select)
        priority_values = parse_multi_filter(priority_filter, IssuePriority.choices)
        if priority_values:
            queryset = queryset.filter(priority__in=priority_values)

        # Apply assignee filter
        if assignee_filter:
            if assignee_filter == "none":
                queryset = queryset.filter(assignee__isnull=True)
            elif assignee_filter.isdigit():
                queryset = queryset.filter(assignee_id=int(assignee_filter))

        return queryset

    def apply_issue_ordering(self, queryset, group_by: str, sort_by: str = ""):
        """Apply ordering based on group_by value and sort_by value.

        When grouping is active, priority is used as the secondary sort for all group_by options
        (except when grouping by priority itself, where created_at is used as secondary sort).

        When no grouping is active, sort_by can be used to customize the sort order.
        """
        from apps.issues.managers import KeyNumber

        if group_by == "project":
            queryset = queryset.annotate(
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by("project__key", "-priority_order", "key_number")
        elif group_by == "epic":
            # Root issues (no epic parent, depth=1) go first, then group by parent epic path
            # For children (depth>1), use the parent's path (first steplen chars) for grouping
            # Then order by priority within each group
            from apps.issues.models import BaseIssue

            steplen = BaseIssue.steplen
            queryset = queryset.annotate(
                has_epic_parent=Case(
                    When(depth=1, then=Value(0)),  # Root = no epic, goes first
                    default=Value(1),
                    output_field=IntegerField(),
                ),
                # For root issues, use own path; for children, use parent's path (first steplen chars)
                epic_group_path=Case(
                    When(depth=1, then=F("path")),
                    default=Substr("path", 1, steplen),
                    output_field=CharField(),
                ),
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by("has_epic_parent", "epic_group_path", "-priority_order", "key_number")
        elif group_by == "status":
            queryset = queryset.annotate(
                status_order=get_status_order_annotation(),
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by("status_order", "-priority_order", "key_number")
        elif group_by == "priority":
            # When grouping by priority, use created_at as secondary sort (priority is already primary)
            queryset = queryset.annotate(
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by("-priority_order", "created_at", "key_number")
        elif group_by == "assignee":
            # Group by assignee_id for proper grouping, order groups alphabetically by name,
            # then order by priority within each group
            queryset = queryset.annotate(
                assignee_name=get_assignee_order_annotation(),
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by(
                F("assignee_name").asc(nulls_first=True),
                F("assignee_id").asc(nulls_first=True),
                "-priority_order",
                "key_number",
            )
        elif group_by == "due_date":
            queryset = queryset.annotate(
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by(
                F("due_date").asc(nulls_last=True),
                "-priority_order",
                "key_number",
            )
        elif group_by == "sprint":
            # Sprint field is only on concrete work item models, not BaseIssue.
            # We can't order by sprint at the queryset level for polymorphic queries.
            # Just order by priority then key and let build_grouped_issues handle the grouping.
            queryset = queryset.annotate(
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            ).order_by("-priority_order", "key_number")
        else:
            # No grouping: apply sort_by if specified, otherwise default to priority then key
            queryset = queryset.annotate(
                priority_order=get_priority_order_annotation(),
                key_number=KeyNumber("key"),
            )
            if sort_by == "title_asc":
                queryset = queryset.order_by("title", "key_number")
            elif sort_by == "title_desc":
                queryset = queryset.order_by("-title", "key_number")
            elif sort_by == "priority_asc":
                queryset = queryset.order_by("priority_order", "key_number")
            elif sort_by == "priority_desc":
                queryset = queryset.order_by("-priority_order", "key_number")
            elif sort_by == "points_asc":
                queryset = queryset.order_by("estimated_points", "key_number")
            elif sort_by == "points_desc":
                queryset = queryset.order_by("-estimated_points", "key_number")
            else:
                # Default: order by priority then key
                queryset = queryset.order_by("-priority_order", "key_number")

        return queryset

    def get_assignee_filter_label(self, assignee_filter: str) -> str:
        """Get the display label for the assignee filter."""
        if not assignee_filter:
            return ""
        if assignee_filter == "none":
            return _("Unassigned")
        if assignee_filter.isdigit():
            assignee_id = int(assignee_filter)
            for member in self.request.workspace_members:
                if member.pk == assignee_id:
                    return member.get_display_name()
        return ""

    def get_issue_list_context(
        self,
        search_query: str,
        status_filter: str,
        type_filter: str,
        assignee_filter: str,
        project_filter: str,
        group_by: str,
        include_group_by: bool = False,
        group_by_in_modal: bool = True,
        extra_group_by_choices: list | None = None,
        sprint_filter: str = "",
        include_sprint_filter: bool = False,
        exclude_epic_group_by: bool = False,
        sort_by: str = "",
        priority_filter: str = "",
        include_priority_filter: bool = False,
        include_type_filter: bool = True,
        type_filter_type: str = "single_select",
        type_filter_choices: list | None = None,
    ) -> dict:
        """Build common context for issue list views."""
        # Build assignee choices from workspace members
        assignee_choices = [("none", _("Unassigned"))]
        for member in self.request.workspace_members:
            assignee_choices.append((str(member.pk), member.get_display_name()))

        # Determine type choices to use
        effective_type_choices = type_filter_choices if type_filter_choices is not None else ISSUE_TYPE_CHOICES

        # Build filter sections for modal
        filter_sections = [
            build_filter_section(
                name="status",
                label=_("Status"),
                filter_type="multi_select",
                choices=IssueStatus.choices,
                current_value=status_filter,
            ),
        ]

        if include_type_filter:
            if type_filter_type == "multi_select":
                filter_sections.append(
                    build_filter_section(
                        name="type",
                        label=_("Type"),
                        filter_type="multi_select",
                        choices=effective_type_choices,
                        current_value=type_filter,
                    )
                )
            else:
                filter_sections.append(
                    build_filter_section(
                        name="type",
                        label=_("Type"),
                        filter_type="single_select",
                        choices=effective_type_choices,
                        current_value=type_filter,
                        empty_label=_("All"),
                    )
                )

        if include_priority_filter:
            filter_sections.append(
                build_filter_section(
                    name="priority",
                    label=_("Priority"),
                    filter_type="multi_select",
                    choices=IssuePriority.choices,
                    current_value=priority_filter,
                )
            )

        filter_sections.append(
            build_filter_section(
                name="assignee",
                label=_("Assignee"),
                filter_type="single_select",
                choices=assignee_choices,
                current_value=assignee_filter,
                empty_label=_("All"),
            ),
        )

        # Add sprint filter section (backlog) when appropriate (project or workspace issues)
        if include_sprint_filter:
            filter_sections.append(
                build_filter_section(
                    name="sprint",
                    label=_("Sprint"),
                    filter_type="single_select",
                    choices=SPRINT_FILTER_CHOICES,
                    current_value=sprint_filter,
                    empty_label=_("All"),
                )
            )

        # Add group_by section when the list is scoped (project detail, sprint detail)
        if (project_filter or include_group_by) and group_by_in_modal:
            filter_sections.append(
                build_filter_section(
                    name="group_by",
                    label=_("Group by"),
                    filter_type="single_select",
                    choices=GROUP_BY_CHOICES,
                    current_value=group_by,
                    empty_label=_("None"),
                )
            )

        # Count active filters (excluding group_by as it's not really a filter)
        active_filters = {"status": status_filter, "assignee": assignee_filter}
        if include_type_filter:
            active_filters["type"] = type_filter
        if include_priority_filter:
            active_filters["priority"] = priority_filter
        if include_sprint_filter:
            active_filters["sprint"] = sprint_filter
        active_filter_count = count_active_filters(active_filters)

        # Build full group-by choices list
        # If exclude_epic_group_by is True and extra_group_by_choices provided, use only extra choices
        # Otherwise, use base choices plus any extras
        if exclude_epic_group_by and extra_group_by_choices:
            all_group_by_choices = list(extra_group_by_choices)
        else:
            all_group_by_choices = list(GROUP_BY_CHOICES)
            if extra_group_by_choices:
                all_group_by_choices.extend(extra_group_by_choices)

        return {
            "priority_choices": IssuePriority.choices,
            "status_choices": IssueStatus.choices,
            "type_choices": effective_type_choices,
            "search_query": search_query,
            "status_filter": status_filter,
            "status_filter_label": get_status_filter_label(status_filter, IssueStatus.choices),
            "type_filter": type_filter,
            "type_filter_label": dict(effective_type_choices).get(type_filter, ""),
            "assignee_filter": assignee_filter,
            "assignee_filter_label": self.get_assignee_filter_label(assignee_filter),
            "priority_filter": priority_filter,
            "sprint_filter": sprint_filter,
            "sprint_filter_label": dict(SPRINT_FILTER_CHOICES).get(sprint_filter, ""),
            "project_filter": project_filter,
            "group_by": group_by,
            "group_by_label": (dict(all_group_by_choices).get(group_by, "") if group_by else ""),
            "group_by_choices": all_group_by_choices,
            "sort_by": sort_by,
            "sort_by_label": dict(SORT_BY_CHOICES).get(sort_by, "") if sort_by else "",
            "sort_by_choices": SORT_BY_CHOICES,
            "filter_sections": filter_sections,
            "active_filter_count": active_filter_count,
        }


class WorkspaceIssueViewMixin:
    """Base mixin for workspace-level issue views (no project required)."""

    model = BaseIssue

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])

    def get_template_names(self):
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        return context


class IssueViewMixin:
    """Base mixin for all issue views."""

    model = BaseIssue

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["project_key"],
        )

    def get_template_names(self):
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        context["project"] = self.project
        return context


class IssueSingleObjectMixin:
    """Mixin for views that operate on a single issue (detail, update, delete)."""

    context_object_name = "issue"
    slug_field = "key"
    slug_url_kwarg = "key"


class IssueFormMixin:
    """Mixin for views with issue forms (create, update)."""

    def get_form_class(self):
        # For update views, use the form class based on the instance type
        if hasattr(self, "object") and self.object:
            issue_type = self.object.get_issue_type()
            return get_form_class_for_type(issue_type)
        # For create views, get type from URL
        issue_type = self.kwargs.get("issue_type", "story")
        return get_form_class_for_type(issue_type)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        kwargs["workspace_members"] = self.request.workspace_members
        return kwargs
