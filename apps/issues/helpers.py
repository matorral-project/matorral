import datetime
from collections import OrderedDict
from functools import lru_cache

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _

from apps.issues.models import STATUS_CATEGORIES, BaseIssue, Epic, IssuePriority, IssueStatus
from apps.utils.filters import parse_status_filter

from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh


@lru_cache(maxsize=1)
def get_epic_content_type_id():
    """Get the ContentType ID for Epic model (cached)."""
    return ContentType.objects.get_for_model(Epic).id


@lru_cache(maxsize=1)
def _get_subtask_content_type_ids():
    """Get ContentType IDs for all issue types that can have subtasks (cached)."""
    from apps.issues.models import Bug, Chore, Story

    return [ContentType.objects.get_for_model(model).id for model in [Story, Bug, Chore]]


def count_subtasks_for_issue_ids(issue_ids):
    """Return count of Subtask objects linked to the given issue IDs via GenericFK."""
    from apps.issues.models import Subtask

    if not issue_ids:
        return 0
    return Subtask.objects.filter(
        content_type_id__in=_get_subtask_content_type_ids(),
        object_id__in=issue_ids,
    ).count()


def delete_subtasks_for_issue_ids(issue_ids):
    """Delete all Subtask objects linked to the given issue IDs via GenericFK. Returns count deleted."""
    from apps.issues.models import Subtask

    if not issue_ids:
        return 0
    deleted, _ = Subtask.objects.filter(
        content_type_id__in=_get_subtask_content_type_ids(),
        object_id__in=issue_ids,
    ).delete()
    return deleted


def build_progress_dict(done_weight: int, in_progress_weight: int, todo_weight: int) -> dict | None:
    """Build a progress dict from pre-computed weights.

    Returns a dict with todo/in_progress/done percentages and weights,
    or None if the total weight is zero.
    """
    total_weight = done_weight + in_progress_weight + todo_weight
    if total_weight == 0:
        return None

    done_pct = round(done_weight / total_weight * 100)
    in_progress_pct = round(in_progress_weight / total_weight * 100)
    todo_pct = 100 - done_pct - in_progress_pct

    return {
        "todo_pct": todo_pct,
        "in_progress_pct": in_progress_pct,
        "done_pct": done_pct,
        "todo_weight": todo_weight,
        "in_progress_weight": in_progress_weight,
        "done_weight": done_weight,
        "total_weight": total_weight,
    }


def calculate_progress(children) -> dict | None:
    """Calculate progress percentages from a list of child issues.

    Each child's weight is its estimated_points if set, otherwise 1.
    Returns a dict with todo/in_progress/done percentages and weights,
    or None if there are no children.
    """
    todo_weight = 0
    in_progress_weight = 0
    done_weight = 0

    for child in children:
        weight = getattr(child, "estimated_points", None) or 1
        category = STATUS_CATEGORIES.get(child.status, "todo")
        if category == "todo":
            todo_weight += weight
        elif category == "in_progress":
            in_progress_weight += weight
        else:
            done_weight += weight

    return build_progress_dict(done_weight, in_progress_weight, todo_weight)


def calculate_valid_page(total_count: int, current_page: int, per_page: int = settings.DEFAULT_PAGE_SIZE) -> int | None:
    """Calculate the valid page to redirect to after items are removed."""
    if total_count == 0:
        return None

    total_pages = (total_count + per_page - 1) // per_page
    return min(current_page, total_pages)


def build_grouped_epics_by_milestone(epics, project, include_empty_milestones: bool = True) -> list[dict]:
    """Build a list of epic groups organized by milestone.

    Args:
        epics: Iterable of Epic objects
        project: Project to include all milestones (even those without epics) when grouping
        include_empty_milestones: If True, include all milestones even if they have no
            matching epics. Set to False when filtering/searching to only show milestones with matching epics.

    Returns:
        List of dicts with keys: milestone (Milestone|None), name (str), epics (list),
        progress (dict|None)
    """
    from apps.issues.models import Milestone

    grouped = OrderedDict()

    # If include_empty_milestones, pre-populate with all project milestones
    if include_empty_milestones:
        all_milestones = Milestone.objects.for_project(project).order_by("key")
        for milestone in all_milestones:
            group_name = f"[{milestone.key}] {milestone.title}"
            grouped[group_name] = {
                "name": group_name,
                "milestone": milestone,
                "epics": [],
                "progress": None,
            }

    # Group epics by milestone
    for epic in epics:
        if epic.milestone:
            group_name = f"[{epic.milestone.key}] {epic.milestone.title}"
            if group_name not in grouped:
                grouped[group_name] = {
                    "name": group_name,
                    "milestone": epic.milestone,
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

    # Calculate progress for each milestone group from descendants of its epics
    for group in grouped.values():
        if group["epics"]:
            epic_paths = [e.path for e in group["epics"]]
            if epic_paths:
                all_children = (
                    BaseIssue.objects.filter(path__regex=r"^(" + "|".join(epic_paths) + r")")
                    .filter(depth__gt=1)  # Exclude the epics themselves
                    .non_polymorphic()
                    .only("status", "estimated_points")
                )
                group["progress"] = calculate_progress(all_children)

    # Sort: milestones by key ascending, with "No Milestone" at the end
    def _milestone_sort_key(group):
        if group["milestone"] is None:
            return (1, "")
        return (0, group["milestone"].key)

    return sorted(grouped.values(), key=_milestone_sort_key)


def annotate_epic_child_counts(epics):
    """Batch-compute child counts for a list of epics using a single query.

    Sets `epic.child_count` on each epic in-place. Uses path-regex matching
    on BaseIssue to count direct children (depth == epic.depth + 1).
    """
    if not epics:
        return

    epic_paths = [e.path for e in epics]
    if not epic_paths:
        return

    # Query all direct children of all epics at once
    all_children = (
        BaseIssue.objects.filter(path__regex=r"^(" + "|".join(epic_paths) + r")")
        .filter(depth=2)  # Direct children of root epics (depth=1)
        .non_polymorphic()
        .only("path")
    )

    # Count children per epic by matching path prefix
    steplen = BaseIssue.steplen
    counts = {}
    for child in all_children:
        parent_path = child.path[:steplen]
        counts[parent_path] = counts.get(parent_path, 0) + 1

    for epic in epics:
        epic.child_count = counts.get(epic.path, 0)


def get_orphan_work_items(project, search_query="", status_filter="", priority_filter="", assignee_filter=""):
    """Query root-level non-epic work items for a project (items with no parent epic).

    Returns a queryset of work items that are root-level (depth=1) and not epics.
    Supports optional search, status, priority, and assignee filtering.
    """
    queryset = (
        BaseIssue.objects.for_project(project)
        .roots()
        .work_items()
        .select_related("project", "project__workspace", "assignee")
    )

    if search_query:
        queryset = queryset.search(search_query)

    status_values = parse_status_filter(status_filter, IssueStatus.choices)
    if status_values:
        queryset = queryset.filter(status__in=status_values)

    if priority_filter:
        priority_values = parse_status_filter(priority_filter, IssuePriority.choices)
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
        steplen = BaseIssue.steplen
        parent_paths = {issue.path[:-steplen] for issue in issues if len(issue.path) > steplen}
        epics_by_path = {epic.path: epic for epic in Epic.objects.filter(path__in=parent_paths)}

        # If milestone is provided and include_empty_epics is True, include only epics linked to that milestone
        if milestone and include_empty_epics:
            all_epics = milestone.epics.order_by("key")
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
            all_epics = Epic.objects.for_project(project).order_by("key")
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
            if isinstance(issue, Epic):
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
            group["progress"] = calculate_progress(group["issues"])

        # Sort epic groups by priority (Critical first, Low last), with "No Epic" at the end
        priority_order = {choice[0]: i for i, choice in enumerate(IssuePriority.choices)}
        max_priority = len(priority_order)

        def _epic_sort_key(group):
            epic = group.get("epic")
            if epic is None:
                return (1, 0)
            # Reverse priority: higher index in choices = higher priority = should come first
            return (0, max_priority - priority_order.get(epic.priority, 0))

        return sorted(grouped.values(), key=_epic_sort_key)

    elif group_by == "status":
        status_labels = dict(IssueStatus.choices)
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, Epic):
                continue
            group_name = status_labels.get(issue.status, issue.status)
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "priority":
        priority_labels = dict(IssuePriority.choices)
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, Epic):
                continue
            priority = getattr(issue, "priority", None)
            group_name = priority_labels.get(priority, str(_("No Priority"))) if priority else str(_("No Priority"))
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "assignee":
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, Epic):
                continue
            assignee = getattr(issue, "assignee", None)
            group_name = assignee.get_display_name() if assignee else str(_("Unassigned"))
            if group_name not in grouped:
                grouped[group_name] = {"name": group_name, "issues": []}
            grouped[group_name]["issues"].append(issue)

    elif group_by == "project":
        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, Epic):
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
        from apps.sprints.models import Sprint, SprintStatus

        # Batch-load sprints to avoid N+1 queries
        sprint_ids = {issue.sprint_id for issue in issues if getattr(issue, "sprint_id", None)}
        sprints_by_id = {}
        if sprint_ids:
            sprints_by_id = {s.pk: s for s in Sprint.objects.filter(pk__in=sprint_ids).select_related("workspace")}

        for issue in issues:
            # Skip epics - they appear as group headers when grouping by epic, not as work items
            if isinstance(issue, Epic):
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
        status_order = {SprintStatus.ACTIVE: 0, SprintStatus.PLANNING: 1}

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
            if isinstance(issue, Epic):
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

    - On the deleted object's detail page → HX-Redirect to ``redirect_url``
      (e.g. the parent's detail page or the project page).
    - On any other page (embedded list, etc.) → HX-Refresh to reload in place.

    ``deleted_object_url`` is the path of the page that no longer exists (the
    deleted object's ``get_absolute_url()``).
    """
    current_path = request.htmx.current_url_abs_path or ""

    if current_path and current_path == deleted_object_url:
        return HttpResponseClientRedirect(redirect_url)
    return HttpResponseClientRefresh()
