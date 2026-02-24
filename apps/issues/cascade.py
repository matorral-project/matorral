"""
Cascade status change service.

Detects and applies cascading status changes when items in the project
hierarchy change status. Supports cascading DOWN (to children) and UP
(to parent) with cross-type status mapping (ProjectStatus <-> IssueStatus <-> SubtaskStatus).
"""

from dataclasses import dataclass, field

from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse
from django.template.loader import render_to_string

from apps.issues.models import BaseIssue, Epic, IssueStatus, Milestone, Subtask, SubtaskStatus
from apps.issues.utils import get_cached_content_type
from apps.projects.models import Project, ProjectStatus
from apps.utils.audit import bulk_create_audit_logs

# Completed status sets per type
COMPLETED_ISSUE_STATUSES = {IssueStatus.DONE, IssueStatus.WONT_DO, IssueStatus.ARCHIVED}
COMPLETED_PROJECT_STATUSES = {ProjectStatus.COMPLETED, ProjectStatus.ARCHIVED}
COMPLETED_SUBTASK_STATUSES = {SubtaskStatus.DONE, SubtaskStatus.WONT_DO}


# ============================================================================
# CASCADE DOWN: eligibility predicates per new status
# ============================================================================

# For IssueStatus targets: which child statuses are eligible?
_ISSUE_CASCADE_DOWN_ELIGIBLE = {
    IssueStatus.DONE: lambda s: s not in COMPLETED_ISSUE_STATUSES,
    IssueStatus.ARCHIVED: lambda s: s not in COMPLETED_ISSUE_STATUSES,
    IssueStatus.WONT_DO: lambda s: s not in COMPLETED_ISSUE_STATUSES,
    IssueStatus.PLANNING: lambda s: s == IssueStatus.DRAFT,
    IssueStatus.READY: lambda s: s in {IssueStatus.DRAFT, IssueStatus.PLANNING},
}

# For SubtaskStatus children when parent moves to an IssueStatus
_SUBTASK_CASCADE_DOWN_ELIGIBLE = {
    IssueStatus.DONE: lambda s: s not in COMPLETED_SUBTASK_STATUSES,
    IssueStatus.ARCHIVED: lambda s: s not in COMPLETED_SUBTASK_STATUSES,
    IssueStatus.WONT_DO: lambda s: s not in COMPLETED_SUBTASK_STATUSES,
}

# Maps an IssueStatus to the target SubtaskStatus for cascade down
_ISSUE_TO_SUBTASK_TARGET = {
    IssueStatus.DONE: SubtaskStatus.DONE,
    IssueStatus.ARCHIVED: SubtaskStatus.DONE,  # No ARCHIVED in SubtaskStatus
    IssueStatus.WONT_DO: SubtaskStatus.WONT_DO,
}

# For ProjectStatus -> IssueStatus cascade down
_PROJECT_TO_ISSUE_TARGET = {
    ProjectStatus.COMPLETED: IssueStatus.DONE,
    ProjectStatus.ARCHIVED: IssueStatus.ARCHIVED,
}

_PROJECT_CASCADE_DOWN_ELIGIBLE = {
    ProjectStatus.COMPLETED: lambda s: s not in COMPLETED_ISSUE_STATUSES,
    ProjectStatus.ARCHIVED: lambda s: s not in COMPLETED_ISSUE_STATUSES,
}


# ============================================================================
# Data classes
# ============================================================================


@dataclass
class CascadeDownGroup:
    """A single group of items in a cascade DOWN (one per model type)."""

    items: list = field(default_factory=list)  # list of model instances
    target_status: str = ""
    target_status_display: str = ""
    model_type: str = ""  # "issue", "milestone", "subtask"


@dataclass
class CascadeDownInfo:
    """Information about a potential cascade DOWN with multiple groups."""

    groups: list = field(default_factory=list)  # list of CascadeDownGroup

    @property
    def total_count(self):
        return sum(len(g.items) for g in self.groups)

    @property
    def all_items(self):
        items = []
        for g in self.groups:
            items.extend(g.items)
        return items

    # Backward-compat properties for single-group access
    @property
    def children(self):
        return self.all_items

    @property
    def target_status(self):
        return self.groups[0].target_status if self.groups else ""

    @property
    def target_status_display(self):
        return self.groups[0].target_status_display if self.groups else ""

    @property
    def model_type(self):
        return self.groups[0].model_type if self.groups else ""


@dataclass
class CascadeUpInfo:
    """Information about a potential cascade UP."""

    parent: object = None
    suggested_status: str = ""
    suggested_status_display: str = ""
    model_type: str = ""  # "project", "milestone", "issue"


@dataclass
class CascadeInfo:
    """Combined cascade information."""

    cascade_down: CascadeDownInfo | None = None
    cascade_up: CascadeUpInfo | None = None

    @property
    def has_cascade(self):
        return self.cascade_down is not None or self.cascade_up is not None


# ============================================================================
# Helper: get children for cascade
# ============================================================================


def _get_subtask_content_type_ids():
    """Get ContentType IDs for work item types that can have subtasks."""
    from apps.issues.models import Bug, Chore, Story

    return [get_cached_content_type(m).id for m in [Story, Bug, Chore]]


def _get_subtasks_for_issue_ids(issue_ids):
    """Get all subtasks for the given issue PKs."""
    if not issue_ids:
        return []
    ct_ids = _get_subtask_content_type_ids()
    return list(Subtask.objects.filter(content_type_id__in=ct_ids, object_id__in=issue_ids))


def get_children_for_cascade(obj):
    """Return children for cascade DOWN, as (queryset_or_list, model_type).

    Returns:
        tuple: (children, model_type) where model_type is 'issue', 'milestone', or 'subtask'
    """
    if isinstance(obj, Project):
        # Project children = milestones + orphan epics (epics without milestone)
        milestones = list(Milestone.objects.for_project(obj))
        orphan_epics = list(Epic.objects.for_project(obj).filter(milestone__isnull=True))
        return milestones + orphan_epics, "mixed_project_children"

    if isinstance(obj, Milestone):
        # Milestone children = epics assigned to it
        epics = list(obj.epics.all())
        return epics, "issue"

    if isinstance(obj, Epic):
        # Epic children = treebeard children (work items)
        children = list(obj.get_children())
        return children, "issue"

    if isinstance(obj, BaseIssue):
        # Work item children = subtasks via GenericFK
        content_type = get_cached_content_type(type(obj))
        subtasks = list(Subtask.objects.filter(content_type=content_type, object_id=obj.pk))
        return subtasks, "subtask"

    if isinstance(obj, Subtask):
        return [], "none"

    return [], "none"


# ============================================================================
# Helper: get parent and siblings for cascade UP
# ============================================================================


def get_parent_and_siblings(obj):
    """Return (parent, siblings) for cascade UP.

    Returns:
        tuple: (parent_instance, siblings_queryset_or_list)
    """
    if isinstance(obj, Subtask):
        # parent = the work item (GenericFK)
        parent = obj.parent
        if parent is None:
            return None, []
        # siblings = other subtasks of same parent
        siblings = Subtask.objects.filter(content_type=obj.content_type, object_id=obj.object_id).exclude(pk=obj.pk)
        return parent, siblings

    if isinstance(obj, BaseIssue):
        real_obj = obj.get_real_instance() if hasattr(obj, "get_real_instance") else obj

        if isinstance(real_obj, Epic):
            if real_obj.milestone_id:
                # Epic with milestone -> parent is milestone
                parent = real_obj.milestone
                siblings = parent.epics.exclude(pk=real_obj.pk)
                return parent, siblings
            else:
                # Orphan epic -> parent is project
                # Siblings = other orphan epics + milestones (ALL must be completed)
                project = real_obj.project
                other_orphan_epics = list(
                    Epic.objects.for_project(project).filter(milestone__isnull=True).exclude(pk=real_obj.pk)
                )
                milestones = list(Milestone.objects.for_project(project))
                return project, other_orphan_epics + milestones
        else:
            # Work item -> parent is epic (treebeard get_parent)
            tree_parent = real_obj.get_parent()
            if tree_parent is None:
                return None, []
            siblings = tree_parent.get_children().exclude(pk=real_obj.pk)
            return tree_parent, siblings

    if isinstance(obj, Milestone):
        # Milestone -> parent is project
        # Siblings = other milestones + orphan epics
        project = obj.project
        other_milestones = list(Milestone.objects.for_project(project).exclude(pk=obj.pk))
        orphan_epics = list(Epic.objects.for_project(project).filter(milestone__isnull=True))
        return project, other_milestones + orphan_epics

    return None, []


# ============================================================================
# Cross-type status mapping
# ============================================================================


def map_status_for_cascade_up(trigger_status, parent):
    """Map a trigger status to the suggested parent status for cascade UP."""
    if isinstance(parent, Project):
        # Child (IssueStatus) -> Project (ProjectStatus)
        mapping = {
            IssueStatus.DONE: ProjectStatus.COMPLETED,
            IssueStatus.ARCHIVED: ProjectStatus.ARCHIVED,
            IssueStatus.WONT_DO: ProjectStatus.COMPLETED,
            IssueStatus.IN_PROGRESS: ProjectStatus.ACTIVE,
        }
        return mapping.get(trigger_status)

    if isinstance(parent, (Milestone, BaseIssue)):
        # Child -> IssueStatus parent
        if trigger_status in (SubtaskStatus.DONE, IssueStatus.DONE):
            return IssueStatus.DONE
        if trigger_status in (SubtaskStatus.WONT_DO, IssueStatus.WONT_DO):
            return IssueStatus.WONT_DO
        if trigger_status == IssueStatus.ARCHIVED:
            return IssueStatus.ARCHIVED
        if trigger_status in (SubtaskStatus.IN_PROGRESS, IssueStatus.IN_PROGRESS):
            return IssueStatus.IN_PROGRESS
        return None

    return None


def _is_completed_status(status, obj):
    """Check if a status is a 'completed' status for the given object type."""
    if isinstance(obj, Project):
        return status in COMPLETED_PROJECT_STATUSES
    if isinstance(obj, Subtask):
        return status in COMPLETED_SUBTASK_STATUSES
    # Milestone or BaseIssue
    return status in COMPLETED_ISSUE_STATUSES


# ============================================================================
# Main detection logic
# ============================================================================


def check_cascade_opportunities(obj, new_status):
    """Check for cascade opportunities after a status change.

    Args:
        obj: The object whose status changed (Project, Milestone, BaseIssue, or Subtask)
        new_status: The new status value

    Returns:
        CascadeInfo with cascade_down and/or cascade_up populated
    """
    info = CascadeInfo()

    # --- CASCADE DOWN ---
    info.cascade_down = _check_cascade_down(obj, new_status)

    # --- CASCADE UP ---
    info.cascade_up = _check_cascade_up(obj, new_status)

    return info


def _check_cascade_down(obj, new_status):
    """Check if cascade DOWN is applicable. Collects ALL descendants, not just direct children."""
    if isinstance(obj, Project):
        return _check_project_cascade_down(obj, new_status)

    if isinstance(obj, Milestone):
        return _check_milestone_cascade_down(obj, new_status)

    if isinstance(obj, Epic):
        return _check_epic_cascade_down(obj, new_status)

    if isinstance(obj, BaseIssue) and not isinstance(obj, Subtask):
        return _check_work_item_cascade_down(obj, new_status)

    return None


def _check_project_cascade_down(project, new_status):
    """Check deep cascade DOWN from Project to all descendants."""
    eligible_pred = _PROJECT_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if eligible_pred is None:
        return None

    issue_target = _PROJECT_TO_ISSUE_TARGET.get(new_status)
    if issue_target is None:
        return None

    issue_choices = dict(IssueStatus.choices)
    subtask_choices = dict(SubtaskStatus.choices)
    groups = []

    # 1. Milestones
    milestones = list(Milestone.objects.for_project(project))
    eligible_milestones = [m for m in milestones if eligible_pred(m.status)]
    if eligible_milestones:
        groups.append(
            CascadeDownGroup(
                items=eligible_milestones,
                target_status=issue_target,
                target_status_display=str(issue_choices.get(issue_target, issue_target)),
                model_type="milestone",
            )
        )

    # 2. All issues in the project
    all_issues = list(BaseIssue.objects.for_project(project).select_related("polymorphic_ctype"))
    eligible_issues = [i for i in all_issues if eligible_pred(i.status)]
    if eligible_issues:
        groups.append(
            CascadeDownGroup(
                items=eligible_issues,
                target_status=issue_target,
                target_status_display=str(issue_choices.get(issue_target, issue_target)),
                model_type="issue",
            )
        )

    # 3. Subtasks of all eligible issues
    eligible_issue_pks = [i.pk for i in eligible_issues]
    subtask_target = _ISSUE_TO_SUBTASK_TARGET.get(issue_target)
    subtask_pred = _SUBTASK_CASCADE_DOWN_ELIGIBLE.get(issue_target)
    if subtask_target and subtask_pred and eligible_issue_pks:
        all_subtasks = _get_subtasks_for_issue_ids(eligible_issue_pks)
        eligible_subtasks = [s for s in all_subtasks if subtask_pred(s.status)]
        if eligible_subtasks:
            groups.append(
                CascadeDownGroup(
                    items=eligible_subtasks,
                    target_status=subtask_target,
                    target_status_display=str(subtask_choices.get(subtask_target, subtask_target)),
                    model_type="subtask",
                )
            )

    if not groups:
        return None

    return CascadeDownInfo(groups=groups)


def _check_milestone_cascade_down(milestone, new_status):
    """Check deep cascade DOWN from Milestone to all descendants."""
    issue_pred = _ISSUE_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if issue_pred is None:
        return None

    issue_choices = dict(IssueStatus.choices)
    subtask_choices = dict(SubtaskStatus.choices)
    groups = []

    # 1. Collect all issues: epics + their descendants
    all_issues = []
    for epic in milestone.epics.all():
        all_issues.append(epic)
        all_issues.extend(epic.get_descendants())

    eligible_issues = [i for i in all_issues if issue_pred(i.status)]
    if eligible_issues:
        groups.append(
            CascadeDownGroup(
                items=eligible_issues,
                target_status=new_status,
                target_status_display=str(issue_choices.get(new_status, new_status)),
                model_type="issue",
            )
        )

    # 2. Subtasks of eligible issues (content type filtering handles epic exclusion)
    eligible_issue_pks = [i.pk for i in eligible_issues]
    subtask_target = _ISSUE_TO_SUBTASK_TARGET.get(new_status)
    subtask_pred = _SUBTASK_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if subtask_target and subtask_pred and eligible_issue_pks:
        all_subtasks = _get_subtasks_for_issue_ids(eligible_issue_pks)
        eligible_subtasks = [s for s in all_subtasks if subtask_pred(s.status)]
        if eligible_subtasks:
            groups.append(
                CascadeDownGroup(
                    items=eligible_subtasks,
                    target_status=subtask_target,
                    target_status_display=str(subtask_choices.get(subtask_target, subtask_target)),
                    model_type="subtask",
                )
            )

    if not groups:
        return None

    return CascadeDownInfo(groups=groups)


def _check_epic_cascade_down(epic, new_status):
    """Check deep cascade DOWN from Epic to all descendants."""
    issue_pred = _ISSUE_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if issue_pred is None:
        return None

    issue_choices = dict(IssueStatus.choices)
    subtask_choices = dict(SubtaskStatus.choices)
    groups = []

    # 1. All descendants via treebeard
    descendants = list(epic.get_descendants())
    eligible_issues = [i for i in descendants if issue_pred(i.status)]
    if eligible_issues:
        groups.append(
            CascadeDownGroup(
                items=eligible_issues,
                target_status=new_status,
                target_status_display=str(issue_choices.get(new_status, new_status)),
                model_type="issue",
            )
        )

    # 2. Subtasks of eligible work items
    eligible_work_item_pks = [i.pk for i in eligible_issues]
    subtask_target = _ISSUE_TO_SUBTASK_TARGET.get(new_status)
    subtask_pred = _SUBTASK_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if subtask_target and subtask_pred and eligible_work_item_pks:
        all_subtasks = _get_subtasks_for_issue_ids(eligible_work_item_pks)
        eligible_subtasks = [s for s in all_subtasks if subtask_pred(s.status)]
        if eligible_subtasks:
            groups.append(
                CascadeDownGroup(
                    items=eligible_subtasks,
                    target_status=subtask_target,
                    target_status_display=str(subtask_choices.get(subtask_target, subtask_target)),
                    model_type="subtask",
                )
            )

    if not groups:
        return None

    return CascadeDownInfo(groups=groups)


def _check_work_item_cascade_down(obj, new_status):
    """Check cascade DOWN from work item to subtasks only."""
    content_type = ContentType.objects.get_for_model(type(obj))
    subtasks = list(Subtask.objects.filter(content_type=content_type, object_id=obj.pk))
    if not subtasks:
        return None

    subtask_pred = _SUBTASK_CASCADE_DOWN_ELIGIBLE.get(new_status)
    if subtask_pred is None:
        return None

    subtask_target = _ISSUE_TO_SUBTASK_TARGET.get(new_status)
    if subtask_target is None:
        return None

    eligible = [s for s in subtasks if subtask_pred(s.status)]
    if not eligible:
        return None

    subtask_choices = dict(SubtaskStatus.choices)
    return CascadeDownInfo(
        groups=[
            CascadeDownGroup(
                items=eligible,
                target_status=subtask_target,
                target_status_display=str(subtask_choices.get(subtask_target, subtask_target)),
                model_type="subtask",
            )
        ]
    )


def _check_cascade_up(obj, new_status):
    """Check if cascade UP is applicable.

    For completed statuses: triggered when ALL siblings are also completed.
    For IN_PROGRESS: triggered immediately (bubbles up without checking siblings).
    """
    in_progress_trigger = (isinstance(obj, Subtask) and new_status == SubtaskStatus.IN_PROGRESS) or (
        isinstance(obj, (BaseIssue, Milestone)) and new_status == IssueStatus.IN_PROGRESS
    )

    if not in_progress_trigger:
        # Completed-status cascade up: check eligibility
        if isinstance(obj, Subtask):
            if new_status not in COMPLETED_SUBTASK_STATUSES:
                return None
        elif isinstance(obj, (BaseIssue, Milestone)):
            if new_status not in COMPLETED_ISSUE_STATUSES:
                return None
        else:
            return None  # Projects don't cascade up

    parent, siblings = get_parent_and_siblings(obj)
    if parent is None:
        return None

    # Check if parent is already completed
    if _is_completed_status(parent.status, parent):
        return None

    if in_progress_trigger:
        # For IN_PROGRESS: only bubble up if parent is in an earlier status
        in_progress_parent_statuses = {
            IssueStatus.DRAFT,
            IssueStatus.PLANNING,
            IssueStatus.READY,
        }
        if isinstance(parent, Project):
            if parent.status != ProjectStatus.DRAFT:
                return None
        elif parent.status not in in_progress_parent_statuses:
            return None
    else:
        # For completed statuses: ALL siblings must also be completed
        for sibling in siblings:
            if not _is_completed_status(sibling.status, sibling):
                return None

    # Offer cascade UP
    suggested = map_status_for_cascade_up(new_status, parent)
    if suggested is None:
        return None

    # Get display name for the suggested status
    if isinstance(parent, Project):
        display = str(dict(ProjectStatus.choices).get(suggested, suggested))
        model_type = "project"
    else:
        display = str(dict(IssueStatus.choices).get(suggested, suggested))
        model_type = "milestone" if isinstance(parent, Milestone) else "issue"

    return CascadeUpInfo(
        parent=parent,
        suggested_status=suggested,
        suggested_status_display=display,
        model_type=model_type,
    )


# ============================================================================
# Apply cascade changes
# ============================================================================


def apply_cascade(
    cascade_down_pks,
    cascade_down_status,
    cascade_down_model_type,
    cascade_up_pk,
    cascade_up_status,
    cascade_up_model_type,
    actor=None,
):
    """Apply cascade status changes.

    Args:
        cascade_down_pks: list of PKs to update for cascade DOWN
        cascade_down_status: target status for cascade DOWN
        cascade_down_model_type: 'issue', 'milestone', 'subtask', or 'project'
        cascade_up_pk: PK of parent to update for cascade UP (or None)
        cascade_up_status: target status for cascade UP
        cascade_up_model_type: 'project', 'milestone', or 'issue'
        actor: User performing the action
    """
    # Apply CASCADE DOWN
    if cascade_down_pks and cascade_down_status:
        _apply_cascade_down(cascade_down_pks, cascade_down_status, cascade_down_model_type, actor)

    # Apply CASCADE UP
    if cascade_up_pk and cascade_up_status:
        _apply_cascade_up(cascade_up_pk, cascade_up_status, cascade_up_model_type, actor)


def _apply_cascade_down(pks, target_status, model_type, actor):
    """Apply cascade DOWN: update children statuses."""
    status_choices = dict(IssueStatus.choices)

    if model_type == "subtask":
        status_choices = dict(SubtaskStatus.choices)
        objects = list(Subtask.objects.filter(pk__in=pks))
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in objects}
        new_display = status_choices.get(target_status, target_status)
        Subtask.objects.filter(pk__in=pks).update(status=target_status)
        bulk_create_audit_logs(objects, "status", old_values, new_display, actor=actor)
    elif model_type == "milestone":
        objects = list(Milestone.objects.filter(pk__in=pks))
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in objects}
        new_display = status_choices.get(target_status, target_status)
        Milestone.objects.filter(pk__in=pks).update(status=target_status)
        bulk_create_audit_logs(objects, "status", old_values, new_display, actor=actor)
    else:
        # "issue" - mixed Milestone + BaseIssue possible (from Project cascade)
        milestone_pks = []
        issue_pks = []
        # Separate milestone PKs from issue PKs
        milestone_pk_set = set(Milestone.objects.filter(pk__in=pks).values_list("pk", flat=True))
        for pk in pks:
            if pk in milestone_pk_set:
                milestone_pks.append(pk)
            else:
                issue_pks.append(pk)

        if milestone_pks:
            m_objects = list(Milestone.objects.filter(pk__in=milestone_pks))
            old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in m_objects}
            new_display = status_choices.get(target_status, target_status)
            Milestone.objects.filter(pk__in=milestone_pks).update(status=target_status)
            bulk_create_audit_logs(m_objects, "status", old_values, new_display, actor=actor)

        if issue_pks:
            i_objects = list(BaseIssue.objects.filter(pk__in=issue_pks).select_related("polymorphic_ctype"))
            old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in i_objects}
            new_display = status_choices.get(target_status, target_status)
            BaseIssue.objects.filter(pk__in=issue_pks).update(status=target_status)
            bulk_create_audit_logs(i_objects, "status", old_values, new_display, actor=actor)


def _apply_cascade_up(pk, target_status, model_type, actor):
    """Apply cascade UP: update parent status."""
    if model_type == "project":
        status_choices = dict(ProjectStatus.choices)
        obj = Project.objects.filter(pk=pk).first()
        if obj:
            old_display = status_choices.get(obj.status, obj.status)
            new_display = status_choices.get(target_status, target_status)
            obj.status = target_status
            obj.save(update_fields=["status", "updated_at"])
            bulk_create_audit_logs([obj], "status", {obj.pk: old_display}, new_display, actor=actor)
    elif model_type == "milestone":
        status_choices = dict(IssueStatus.choices)
        obj = Milestone.objects.filter(pk=pk).first()
        if obj:
            old_display = status_choices.get(obj.status, obj.status)
            new_display = status_choices.get(target_status, target_status)
            obj.status = target_status
            obj.save(update_fields=["status", "updated_at"])
            bulk_create_audit_logs([obj], "status", {obj.pk: old_display}, new_display, actor=actor)
    else:
        # "issue" - BaseIssue subclass
        status_choices = dict(IssueStatus.choices)
        obj = BaseIssue.objects.filter(pk=pk).select_related("polymorphic_ctype").first()
        if obj:
            old_display = status_choices.get(obj.status, obj.status)
            new_display = status_choices.get(target_status, target_status)
            obj.status = target_status
            obj.save(update_fields=["status", "updated_at"])
            bulk_create_audit_logs([obj], "status", {obj.pk: old_display}, new_display, actor=actor)


# ============================================================================
# OOB response builders
# ============================================================================


def build_cascade_oob_response(request, obj, new_status, response):
    """Append OOB cascade modal content + HX-Trigger to an existing HttpResponse.

    For single-object status changes (inline edits).
    Returns the response unmodified if no cascade is applicable.
    """
    cascade_info = check_cascade_opportunities(obj, new_status)
    if not cascade_info.has_cascade:
        return response

    return _append_cascade_oob(request, cascade_info, response)


def build_cascade_oob_response_bulk(request, objects, new_status, response):
    """Build cascade OOB response for bulk status changes.

    Groups cascade UP checks by parent. Cascade DOWN aggregates all children.
    """
    if not objects:
        return response

    # Aggregate cascade DOWN across all objects - merge groups by model_type
    # Key: model_type -> {items: [], target_status, target_status_display}
    merged_groups = {}

    # Aggregate cascade UP - group by parent
    up_candidates = []

    for obj in objects:
        info = check_cascade_opportunities(obj, new_status)
        if info.cascade_down:
            for group in info.cascade_down.groups:
                if group.model_type not in merged_groups:
                    merged_groups[group.model_type] = {
                        "items": [],
                        "seen_pks": set(),
                        "target_status": group.target_status,
                        "target_status_display": group.target_status_display,
                        "model_type": group.model_type,
                    }
                mg = merged_groups[group.model_type]
                for item in group.items:
                    if item.pk not in mg["seen_pks"]:
                        mg["seen_pks"].add(item.pk)
                        mg["items"].append(item)
        if info.cascade_up:
            up_candidates.append(info.cascade_up)

    # Deduplicate up candidates by parent PK - pick the first suggestion
    seen_parent_pks = set()
    unique_up = None
    for up in up_candidates:
        if up.parent.pk not in seen_parent_pks:
            seen_parent_pks.add(up.parent.pk)
            unique_up = up  # Take just the first for simplicity
            break

    combined = CascadeInfo()
    if merged_groups:
        groups = [
            CascadeDownGroup(
                items=mg["items"],
                target_status=mg["target_status"],
                target_status_display=mg["target_status_display"],
                model_type=mg["model_type"],
            )
            for mg in merged_groups.values()
            if mg["items"]
        ]
        if groups:
            combined.cascade_down = CascadeDownInfo(groups=groups)
    if unique_up:
        combined.cascade_up = unique_up

    if not combined.has_cascade:
        return response

    return _append_cascade_oob(request, combined, response)


def _append_cascade_oob(request, cascade_info, response):
    """Append OOB HTML and HX-Trigger header to response."""
    context = _build_cascade_context(request, cascade_info)

    # Render the cascade modal content
    html = render_to_string(
        "issues/includes/cascade_status_content.html",
        context,
        request=request,
    )

    # Wrap in OOB swap div
    oob_html = f'<div id="cascade-modal-content" hx-swap-oob="true">{html}</div>'

    # Append to response content
    if isinstance(response.content, bytes):
        response.content = response.content + oob_html.encode("utf-8")
    else:
        response.content = response.content + oob_html

    # Set HX-Trigger to open the modal
    existing_trigger = response.get("HX-Trigger", "")
    if existing_trigger:
        response["HX-Trigger"] = f"{existing_trigger}, show-cascade-modal"
    else:
        response["HX-Trigger"] = "show-cascade-modal"

    return response


def _build_cascade_context(request, cascade_info):
    """Build template context for cascade modal content."""
    from django.urls import reverse

    context = {
        "cascade_down": None,
        "cascade_up": None,
    }

    if cascade_info.cascade_down:
        down = cascade_info.cascade_down
        max_display = 10
        all_items = down.all_items
        # Build per-group data for indexed hidden fields
        groups_data = []
        for group in down.groups:
            groups_data.append(
                {
                    "child_pks": ",".join(str(c.pk) for c in group.items),
                    "target_status": group.target_status,
                    "model_type": group.model_type,
                }
            )
        context["cascade_down"] = {
            "total_count": down.total_count,
            "target_status_display": (down.groups[0].target_status_display if down.groups else ""),
            "children_display": all_items[:max_display],
            "children_remaining": max(0, len(all_items) - max_display),
            "groups": groups_data,
            "down_group_count": len(groups_data),
        }

    if cascade_info.cascade_up:
        up = cascade_info.cascade_up
        context["cascade_up"] = {
            "parent": up.parent,
            "parent_display": str(up.parent),
            "suggested_status": up.suggested_status,
            "suggested_status_display": up.suggested_status_display,
            "model_type": up.model_type,
            "parent_pk": up.parent.pk,
        }

    # Build the apply URL - we need workspace_slug from the request
    workspace_slug = request.resolver_match.kwargs.get("workspace_slug", "")
    if workspace_slug:
        context["apply_url"] = reverse(
            "cascade_status_apply",
            kwargs={"workspace_slug": workspace_slug},
        )
    else:
        context["apply_url"] = ""

    return context


def build_cascade_retarget_response(request, obj, new_status):
    """Build a response that renders cascade modal content using HX-Retarget.

    Used when cascade needs to be shown from a modal form submission (e.g.,
    edit modal via 3-dots menu). Uses HX-Retarget to swap cascade content
    directly into #cascade-modal-content, avoiding OOB swaps that fail when
    the triggering form element is detached from the DOM.

    Returns an HttpResponse if cascade is applicable, or None otherwise.
    """
    cascade_info = check_cascade_opportunities(obj, new_status)
    if not cascade_info.has_cascade:
        return None

    context = _build_cascade_context(request, cascade_info)
    html = render_to_string(
        "issues/includes/cascade_status_content.html",
        context,
        request=request,
    )

    response = HttpResponse(html)
    response["HX-Retarget"] = "#cascade-modal-content"
    response["HX-Reswap"] = "innerHTML"
    response["HX-Trigger"] = "show-cascade-modal"
    return response
