import datetime
import json
from collections import OrderedDict
from functools import lru_cache

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from apps.issues import models
from apps.sprints import models as sprints_models
from apps.utils.filters import parse_status_filter
from apps.utils.progress import build_progress_dict, calculate_progress

from django_htmx.http import HttpResponseClientRefresh


@lru_cache(maxsize=1)
def get_epic_content_type_id():
    """Get the ContentType ID for Epic model (cached)."""
    return ContentType.objects.get_for_model(models.Epic).id


@lru_cache(maxsize=1)
def get_milestone_content_type_id():
    """Get the ContentType ID for Milestone model (cached)."""
    return ContentType.objects.get_for_model(models.Milestone).id


def get_issue_creation_defaults(model_class, project, workspace_members) -> dict:
    """Return preset initial values for issue creation forms.

    Presets assignee (single-member auto-select or latest item's assignee), priority,
    estimated_points (work items), and severity (bugs) scoped to the given project.
    """
    initial = {}

    # Workspace-level: auto-select assignee for single-member workspaces
    if workspace_members and len(workspace_members) == 1:
        initial["assignee"] = workspace_members[0].pk

    if model_class:
        fields = ["priority", "due_date", "assignee_id"]

        if model_class in (models.Story, models.Bug, models.Chore):
            # Work items: Story, Bug, and Chore
            fields.extend(["estimated_points"])

            if model_class is models.Bug:
                fields.append("severity")

        base_qs = model_class.objects
        if project:
            base_qs = base_qs.for_project(project)

        try:
            latest = base_qs.values(*fields).latest("created_at")
        except model_class.DoesNotExist:
            latest = None

        if latest:
            if "assignee" not in initial and latest["assignee_id"]:
                initial["assignee"] = latest["assignee_id"]
            if latest["priority"]:
                initial["priority"] = latest["priority"]
            if "estimated_points" in fields and latest.get("estimated_points"):
                initial["estimated_points"] = latest["estimated_points"]
            if "severity" in fields and latest.get("severity"):
                initial["severity"] = latest["severity"]
            if "due_date" in fields and latest.get("due_date"):
                initial["due_date"] = latest["due_date"].strftime("%Y-%m-%d")

    return initial


def calculate_valid_page(total_count: int, current_page: int, per_page: int = settings.DEFAULT_PAGE_SIZE) -> int | None:
    """Calculate the valid page to redirect to after items are removed."""
    if total_count == 0:
        return None

    total_pages = (total_count + per_page - 1) // per_page
    return min(current_page, total_pages)


def build_grouped_epics_by_milestone(epics, project, include_empty_milestones: bool = True) -> list[dict]:
    """Build a list of epic groups organized by milestone (tree parent).

    Args:
        epics: Iterable of Epic objects
        project: Project to include all milestones (even those without epics) when grouping
        include_empty_milestones: If True, include all milestones even if they have no
            matching epics. Set to False when filtering/searching to only show milestones with matching epics.

    Returns:
        List of dicts with keys: milestone (Milestone|None), name (str), epics (list),
        progress (dict|None)
    """
    epics = list(epics)

    # Batch-load parent milestones to avoid N+1 queries
    parents_by_pk = models.BaseIssue.batch_load_parents(epics)

    grouped = OrderedDict()

    # If include_empty_milestones, pre-populate with all project milestones
    if include_empty_milestones:
        all_milestones = models.Milestone.objects.for_project(project).order_by("key")
        for milestone in all_milestones:
            group_name = f"[{milestone.key}] {milestone.title}"
            grouped[group_name] = {
                "name": group_name,
                "milestone": milestone,
                "epics": [],
                "progress": None,
            }

    # Group epics by tree parent milestone
    for epic in epics:
        parent_milestone = parents_by_pk.get(epic.pk)

        if parent_milestone:
            group_name = f"[{parent_milestone.key}] {parent_milestone.title}"
            if group_name not in grouped:
                grouped[group_name] = {
                    "name": group_name,
                    "milestone": parent_milestone,
                    "epics": [],
                    "progress": None,
                }
            grouped[group_name]["epics"].append(epic)
        else:
            # No Milestone group
            no_milestone_name = str(_("No Milestone"))
            if no_milestone_name not in grouped:
                grouped[no_milestone_name] = {
                    "name": no_milestone_name,
                    "milestone": None,
                    "epics": [],
                    "progress": None,
                }
            grouped[no_milestone_name]["epics"].append(epic)

    # Calculate progress for each milestone group from the epic annotations
    for group in grouped.values():
        if group["epics"]:
            # Sum progress from all epics in this group
            total_done = sum(getattr(e, "total_done_points", 0) or 0 for e in group["epics"])
            total_in_progress = sum(getattr(e, "total_in_progress_points", 0) or 0 for e in group["epics"])
            total_todo = sum(getattr(e, "total_todo_points", 0) or 0 for e in group["epics"])
            total = sum(getattr(e, "total_estimated_points", 0) or 0 for e in group["epics"])
            group["progress"] = build_progress_dict(total_done, total_in_progress, total_todo, total)

    # Sort: milestones by key ascending, with "No Milestone" at the end
    def _milestone_sort_key(group):
        if group["milestone"] is None:
            return (1, "")
        return (0, group["milestone"].key)

    return sorted(grouped.values(), key=_milestone_sort_key)


def annotate_epic_child_counts(epics):
    """Batch-compute child counts for a list of epics using a single query.

    Sets `epic.child_count` on each epic in-place. Uses path-prefix matching
    on BaseIssue to count direct children at any depth.
    """
    if not epics:
        return

    epic_paths = [e.path for e in epics]
    if not epic_paths:
        return

    epic_paths_set = set(epic_paths)
    steplen = models.BaseIssue.steplen

    # Query all descendants of all epics at once (no depth filter — epics can be at any depth)
    all_descendants = (
        models.BaseIssue.objects.filter(path__regex=r"^(" + "|".join(epic_paths) + r")").non_polymorphic().only("path")
    )

    # Count only direct children (parent path is exactly epic.path)
    counts = {}
    for descendant in all_descendants:
        parent_path = descendant.path[:-steplen]
        if parent_path in epic_paths_set:
            counts[parent_path] = counts.get(parent_path, 0) + 1

    for epic in epics:
        epic.child_count = counts.get(epic.path, 0)


def get_orphan_work_items(project, search_query="", status_filter="", priority_filter="", assignee_filter=""):
    """Query root-level non-epic work items for a project (items with no parent epic).

    Returns a queryset of work items that are root-level (depth=1) and not epics.
    Supports optional search, status, priority, and assignee filtering.
    """
    queryset = (
        models.BaseIssue.objects.for_project(project)
        .roots()
        .work_items()
        .select_related("project", "project__workspace", "assignee")
    )

    if search_query:
        queryset = queryset.search(search_query)

    status_values = parse_status_filter(status_filter, models.IssueStatus.choices)
    if status_values:
        queryset = queryset.filter(status__in=status_values)

    if priority_filter:
        priority_values = parse_status_filter(priority_filter, models.IssuePriority.choices)
        if priority_values:
            queryset = queryset.filter(priority__in=priority_values)

    if assignee_filter:
        if assignee_filter == "none":
            queryset = queryset.filter(assignee__isnull=True)
        elif assignee_filter.isdigit():
            queryset = queryset.filter(assignee_id=int(assignee_filter))

    return queryset.order_by("key")


def build_grouped_issues(
    issues,
    group_by: str,
    project=None,
    milestone=None,
    include_empty_epics: bool = True,
) -> list[dict]:
    """Build a list of issue groups organized by the selected field.

    Args:
        issues: Iterable of issue objects
        group_by: Field to group by ("epic", "status", "priority", "assignee")
        project: Optional project to include all epics (even those without children) when grouping by epic
        milestone: Optional milestone to include only its linked epics when grouping by epic
        include_empty_epics: If True and project/milestone is provided, include all epics even if they have no
            matching issues. Set to False when filtering/searching to only show epics with matching issues.

    Returns:
        List of dicts with keys: name (str), issues (list), epic_key (str|None),
        epic (Epic|None, only for epic grouping)
    """
    grouped = OrderedDict()

    if group_by == "epic":
        # Prefetch all parent epics in one query to avoid N+1
        steplen = models.BaseIssue.steplen
        parent_paths = {issue.path[:-steplen] for issue in issues if len(issue.path) > steplen}
        epics_by_path = {epic.path: epic for epic in models.Epic.objects.filter(path__in=parent_paths)}

        # If milestone is provided and include_empty_epics is True, include only epics that are direct children
        if milestone and include_empty_epics:
            all_epics = milestone.get_children().instance_of(models.Epic).order_by("key")
            for epic in all_epics:
                epics_by_path[epic.path] = epic
                group_name = f"[{epic.key}] {epic.title}"
                if group_name not in grouped:
                    grouped[group_name] = {
                        "name": group_name,
                        "issues": [],
                        "epic_key": epic.key,
                        "epic": epic,
                    }

        # If project is provided and include_empty_epics is True, include all epics (even those without children)
        elif project and include_empty_epics:
            all_epics = models.Epic.objects.for_project(project).order_by("key")
            for epic in all_epics:
                epics_by_path[epic.path] = epic
                group_name = f"[{epic.key}] {epic.title}"
                if group_name not in grouped:
                    grouped[group_name] = {
                        "name": group_name,
                        "issues": [],
                        "epic_key": epic.key,
                        "epic": epic,
                    }

        for issue in issues:
            # Skip epics - they appear as group headers, not as items
            if isinstance(issue, models.Epic):
                continue

            parent_path = issue.path[:-steplen] if len(issue.path) > steplen else None
            parent = epics_by_path.get(parent_path) if parent_path else None
            group_name = f"[{parent.key}] {parent.title}" if parent else str(_("No Epic"))
            epic_key = parent.key if parent else None
            if group_name not in grouped:
                grouped[group_name] = {
                    "name": group_name,
                    "issues": [],
                    "epic_key": epic_key,
                    "epic": parent,
                }
            grouped[group_name]["issues"].append(issue)

        # Calculate progress for each epic group from its issues list
        for group in grouped.values():
            epic = group.get("epic")
            if epic is not None:
                # Calculate progress from the issues in the group
                group["progress"] = calculate_progress(group["issues"])

        # Sort epic groups by priority (Critical first, Low last), with "No Epic" at the end
        priority_order = {choice[0]: i for i, choice in enumerate(models.IssuePriority.choices)}
        max_priority = len(priority_order)

        def _epic_sort_key(group):
            epic = group.get("epic")
            if epic is None:
                return (1, 0)
            # Reverse priority: higher index in choices = higher priority = should come first
            return (0, max_priority - priority_order.get(epic.priority, 0))

        return sorted(grouped.values(), key=_epic_sort_key)

    elif group_by == "status":
        status_labels = dict(models.IssueStatus.choices)
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, models.Epic):
                continue
            group_name = status_labels.get(issue.status, issue.status)
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "priority":
        priority_labels = dict(models.IssuePriority.choices)
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, models.Epic):
                continue
            priority = getattr(issue, "priority", None)
            group_name = priority_labels.get(priority, str(_("No Priority"))) if priority else str(_("No Priority"))
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "assignee":
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, models.Epic):
                continue
            assignee = getattr(issue, "assignee", None)
            group_name = assignee.get_display_name() if assignee else str(_("Unassigned"))
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "project":
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, models.Epic):
                continue
            project = getattr(issue, "project", None)
            group_name = f"[{project.key}] {project.name}" if project else str(_("No Project"))
            if group_name not in grouped:
                grouped[group_name] = {
                    "name": group_name,
                    "issues": [],
                    "project": project,
                }
            grouped[group_name]["issues"].append(issue)

    elif group_by == "sprint":
        # Batch-load sprints to avoid N+1 queries
        sprint_ids = {issue.sprint_id for issue in issues if getattr(issue, "sprint_id", None)}
        sprints_by_id = {}
        if sprint_ids:
            sprints_by_id = {
                s.pk: s for s in sprints_models.Sprint.objects.filter(pk__in=sprint_ids).select_related("workspace")
            }

        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, models.Epic):
                continue
            sprint = sprints_by_id.get(issue.sprint_id) if getattr(issue, "sprint_id", None) else None
            group_name = f"[{sprint.key}] {sprint.name}" if sprint else str(_("No Sprint"))
            if group_name not in grouped:
                grouped[group_name] = {
                    "name": group_name,
                    "issues": [],
                    "sprint": sprint,
                }
            grouped[group_name]["issues"].append(issue)

        # Sort: active sprints first, then planning, then by key number, "No Sprint" at end
        status_order = {sprints_models.SprintStatus.ACTIVE: 0, sprints_models.SprintStatus.PLANNING: 1}

        def _sprint_sort_key(group):
            sprint = group.get("sprint")
            if sprint is None:
                return (2, 0)
            try:
                key_num = int(sprint.key.rsplit("-", 1)[1])
            except (IndexError, ValueError):
                key_num = 0
            return (status_order.get(sprint.status, 1), key_num)

        return sorted(grouped.values(), key=_sprint_sort_key)

    elif group_by == "due_date":
        today = datetime.date.today()
        this_week_end = today + datetime.timedelta(days=7)

        bucket_labels = [
            str(_("Overdue")),
            str(_("Today")),
            str(_("This Week")),
            str(_("Later")),
            str(_("No Date")),
        ]

        for issue in issues:
            if isinstance(issue, models.Epic):
                continue
            due = getattr(issue, "due_date", None)
            if due is None:
                bucket = bucket_labels[4]
            elif due < today:
                bucket = bucket_labels[0]
            elif due == today:
                bucket = bucket_labels[1]
            elif due <= this_week_end:
                bucket = bucket_labels[2]
            else:
                bucket = bucket_labels[3]
            if bucket not in grouped:
                grouped[bucket] = {"name": bucket, "issues": []}
            grouped[bucket]["issues"].append(issue)

        return [grouped[b] for b in bucket_labels if b in grouped]

    return list(grouped.values())


def build_htmx_delete_response(request, deleted_object_url, redirect_url):
    """Build the appropriate HTMX response after deleting an object.

    Determines whether the user is on the deleted object's own page or on a
    parent/list page, and returns the right HTMX header:

    - On the deleted object's detail page → HX-Location to ``redirect_url``
      (e.g. the parent's detail page or the project page).
    - On any other page (embedded list, etc.) → HX-Refresh to reload in place.

    ``deleted_object_url`` is the path of the page that no longer exists (the
    deleted object's ``get_absolute_url()``.
    """

    current_path = request.htmx.current_url_abs_path or ""

    if current_path and current_path == deleted_object_url:
        # Use HX-Location with target="#page-content" to swap only the main content
        location_data = json.dumps({"path": redirect_url, "target": "#page-content"})
        response = HttpResponse(status=200)
        response["HX-Location"] = location_data
        return response
    return HttpResponseClientRefresh()
