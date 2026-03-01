from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.cascade import build_cascade_oob_response_bulk
from apps.issues.forms import WorkspaceBulkActionForm, WorkspaceBulkAssigneeForm, WorkspaceBulkMilestoneForm
from apps.issues.helpers import (
    build_grouped_epics_by_milestone,
    build_grouped_issues,
    calculate_valid_page,
    count_subtasks_for_issue_ids,
    delete_subtasks_for_issue_ids,
)
from apps.issues.models import BaseIssue, Bug, Chore, Epic, IssuePriority, IssueStatus, Milestone, Story
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.audit import bulk_create_audit_logs
from apps.utils.filters import get_status_filter_label, parse_status_filter
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from .mixins import WORK_ITEM_TYPE_CHOICES, IssueListContextMixin, WorkspaceIssueViewMixin

# ============================================================================
# Workspace-level bulk actions (across all projects in a workspace)
# ============================================================================


def _get_workspace_redirect_url_with_page(workspace_slug: str, page: int | None) -> str:
    """Build redirect URL for workspace issue list, preserving page if valid."""
    url = reverse("workspace_issue_list", kwargs={"workspace_slug": workspace_slug})
    if page and page > 1:
        url = f"{url}?page={page}"
    return url


class WorkspaceBulkActionMixin(IssueListContextMixin, WorkspaceIssueViewMixin):
    """Base mixin for bulk operations on issues at the workspace level."""

    http_method_names = ["post"]
    form_class = WorkspaceBulkActionForm

    def get_queryset(self):
        return BaseIssue.objects.for_workspace(self.workspace)

    def get_selected_queryset(self):
        # ModelMultipleChoiceField returns a queryset of selected objects
        return self.form.cleaned_data["issues"]

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "queryset": self.get_queryset(),
        }

    def get_form(self):
        return self.form_class(**self.get_form_kwargs())

    def post(self, request, *args, **kwargs):
        self.form = self.get_form()
        if not self.form.is_valid():
            for errors in self.form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return self.render_response(int(request.POST.get("page", 1)))

        if not self.form.cleaned_data["issues"]:
            messages.warning(request, _("No issues selected."))
            return self.render_response(self.form.cleaned_data["page"])

        redirect_page = self.perform_action()
        return self.render_response(redirect_page)

    def perform_action(self):
        """Subclasses implement this. Returns the page to redirect to."""
        raise NotImplementedError

    def render_response(self, page):
        # Check if this is an embed request
        embed_value = self.request.POST.get("embed", "")
        is_sprint_embed = embed_value == "sprint"
        is_epic_embed = embed_value == "epic"
        is_milestone_embed = embed_value == "milestone"
        is_project_epics_embed = embed_value == "project_epics"
        is_project_orphan_embed = embed_value == "project_orphan"

        if not self.request.htmx:
            return redirect(
                _get_workspace_redirect_url_with_page(
                    self.kwargs["workspace_slug"],
                    page,
                )
            )

        # Extract filter values from form
        search_query = self.form.cleaned_data.get("search", "")
        status_filter = self.form.cleaned_data.get("status_filter", "")
        type_filter = self.form.cleaned_data.get("type_filter", "")
        assignee_filter = self.form.cleaned_data.get("assignee_filter", "")
        project_filter = self.form.cleaned_data.get("project_filter", "")
        sprint_filter = self.form.cleaned_data.get("sprint_filter", "")
        epic_filter = self.form.cleaned_data.get("epic_filter", "")
        milestone_filter = self.form.cleaned_data.get("milestone_filter", "")
        priority_filter = self.form.cleaned_data.get("priority_filter", "")
        # Group by is only available when filtering by project, sprint, epic, or milestone
        group_by = (
            self.form.cleaned_data.get("group_by", "")
            if (project_filter or sprint_filter or epic_filter or milestone_filter)
            else ""
        )

        # Build queryset based on context
        if is_project_epics_embed and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            queryset = Epic.objects.for_project(project).select_related(
                "project", "project__workspace", "assignee", "milestone"
            )
        elif is_sprint_embed and sprint_filter:
            sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=sprint_filter)
            queryset = BaseIssue.objects.for_sprint(sprint).select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )
        elif is_epic_embed and epic_filter and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            epic = get_object_or_404(Epic.objects.for_project(project), key=epic_filter)
            queryset = epic.get_children().select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )
        elif is_milestone_embed and milestone_filter and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            milestone = get_object_or_404(Milestone.objects.for_project(project), key=milestone_filter)
            queryset = BaseIssue.objects.for_milestone(milestone).select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )
        elif is_project_orphan_embed and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            queryset = (
                BaseIssue.objects.for_project(project)
                .roots()
                .work_items()
                .select_related("project", "project__workspace", "assignee", "polymorphic_ctype")
            )
        else:
            queryset = self.get_queryset().select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )

        # Apply filters and ordering using mixin methods
        queryset = self.apply_issue_filters(queryset, type_filter, search_query, status_filter, assignee_filter)
        queryset = self.apply_issue_ordering(queryset, group_by)

        # Build context using mixin method
        context = {
            "workspace": self.workspace,
            "workspace_members": self.request.workspace_members,
        }

        if is_project_orphan_embed:
            orphan_group_by_choices = [
                ("status", _("Status")),
                ("priority", _("Priority")),
                ("assignee", _("Assignee")),
                ("due_date", _("Due Date")),
            ]
            context.update(
                self.get_issue_list_context(
                    search_query,
                    status_filter,
                    type_filter,
                    assignee_filter,
                    project_filter,
                    group_by,
                    group_by_in_modal=False,
                    sprint_filter=sprint_filter,
                    include_sprint_filter=True,
                    extra_group_by_choices=orphan_group_by_choices,
                    exclude_epic_group_by=True,
                    priority_filter=priority_filter,
                    include_priority_filter=True,
                    type_filter_type="multi_select",
                    type_filter_choices=WORK_ITEM_TYPE_CHOICES,
                )
            )
        else:
            context.update(
                self.get_issue_list_context(
                    search_query,
                    status_filter,
                    type_filter,
                    assignee_filter,
                    project_filter,
                    group_by,
                    include_group_by=is_sprint_embed,
                    group_by_in_modal=False,
                    extra_group_by_choices=([("project", _("Project"))] if is_sprint_embed else None),
                )
            )

        # Handle pagination based on grouping
        if group_by:
            issues = list(queryset)
            context["issues"] = issues
            context["is_paginated"] = False
            context["grouped_issues"] = build_grouped_issues(issues, group_by)
        else:
            paginator = Paginator(queryset, settings.DEFAULT_PAGE_SIZE)
            page_obj = paginator.get_page(page or 1)
            context["issues"] = page_obj
            context["page_obj"] = page_obj
            context["paginator"] = paginator
            context["is_paginated"] = page_obj.has_other_pages()
            if context["is_paginated"]:
                context["elided_page_range"] = paginator.get_elided_page_range(
                    page_obj.number, on_each_side=2, on_ends=1
                )

        # For project epics embed mode, render the epics grouped by milestone
        if is_project_epics_embed and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            context["project"] = project
            context["search_query"] = search_query
            context["status_filter"] = status_filter
            context["status_filter_label"] = get_status_filter_label(status_filter, IssueStatus.choices)
            context["priority_filter"] = priority_filter
            context["priority_filter_label"] = get_status_filter_label(priority_filter, IssuePriority.choices)
            context["assignee_filter"] = assignee_filter
            context["status_choices"] = IssueStatus.choices
            context["priority_choices"] = IssuePriority.choices

            # Apply filters to the queryset for project_epics
            epics_queryset = queryset
            if search_query:
                epics_queryset = epics_queryset.search(search_query)
            status_values = parse_status_filter(status_filter, IssueStatus.choices)
            if status_values:
                epics_queryset = epics_queryset.filter(status__in=status_values)
            if priority_filter:
                priority_values = parse_status_filter(priority_filter, IssuePriority.choices)
                if priority_values:
                    epics_queryset = epics_queryset.filter(priority__in=priority_values)
            if assignee_filter:
                if assignee_filter == "none":
                    epics_queryset = epics_queryset.filter(assignee__isnull=True)
                elif assignee_filter.isdigit():
                    epics_queryset = epics_queryset.filter(assignee_id=int(assignee_filter))

            context["epics"] = epics_queryset
            # Build grouped epics by milestone
            has_active_filters = bool(search_query or status_filter or priority_filter or assignee_filter)
            context["grouped_epics"] = build_grouped_epics_by_milestone(
                epics_queryset,
                project=project,
                include_empty_milestones=not has_active_filters,
            )
            context["embed_url"] = reverse(
                "projects:project_epics_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": project.key,
                },
            )
            context["project_milestones"] = Milestone.objects.for_project(project).for_choices()
            return render(self.request, "projects/project_epics_embed.html#embed-content", context)

        # For sprint embed mode, render the shared embedded template with sprint context
        if is_sprint_embed and sprint_filter:
            context["sprint"] = sprint
            context["embed_url"] = reverse(
                "sprints:sprint_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": sprint.key,
                },
            )
            return render(self.request, "issues/issues_embed.html#embed-content", context)

        # For epic embed mode, render the shared embedded template with epic context
        if is_epic_embed and epic_filter and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            epic = get_object_or_404(Epic.objects.for_project(project), key=epic_filter)
            context["epic"] = epic
            context["project"] = project
            context["available_sprints"] = (
                Sprint.objects.for_workspace(self.workspace)
                .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
                .order_by("-status", "-start_date")
            )
            # Build group-by choices for epic context: exclude "epic", add "sprint"
            epic_group_by_choices = [
                ("sprint", _("Sprint")),
                ("status", _("Status")),
                ("priority", _("Priority")),
                ("assignee", _("Assignee")),
            ]
            context["group_by_choices"] = epic_group_by_choices
            context["embed_url"] = reverse(
                "issues:epic_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "project_key": project.key,
                    "key": epic.key,
                },
            )
            return render(self.request, "issues/issues_embed.html#embed-content", context)

        # For milestone embed mode, render the shared embedded template with milestone context
        if is_milestone_embed and milestone_filter and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            milestone = get_object_or_404(Milestone.objects.for_project(project), key=milestone_filter)
            context["milestone"] = milestone
            context["project"] = project
            context["available_sprints"] = (
                Sprint.objects.for_workspace(self.workspace)
                .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
                .order_by("-status", "-start_date")
            )
            # Rebuild grouped_issues with milestone context for epic grouping
            if group_by and "grouped_issues" in context:
                context["grouped_issues"] = build_grouped_issues(
                    context["issues"], group_by, project=project, milestone=milestone
                )
            context["embed_url"] = reverse(
                "milestones:milestone_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "project_key": project.key,
                    "key": milestone.key,
                },
            )
            return render(self.request, "issues/issues_embed.html#embed-content", context)

        # For project orphan embed mode, render the shared embedded template with project_orphan context
        if is_project_orphan_embed and project_filter:
            project = get_object_or_404(Project.objects.for_workspace(self.workspace), key=project_filter)
            context["project"] = project
            context["project_orphan"] = True
            context["available_sprints"] = (
                Sprint.objects.for_workspace(self.workspace)
                .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
                .order_by("-status", "-start_date")
            )
            context["embed_url"] = reverse(
                "projects:project_orphan_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": project.key,
                },
            )
            return render(self.request, "issues/issues_embed.html#embed-content", context)

        return render(self.request, "issues/workspace_issue_list.html#page-content", context)


class WorkspaceIssueBulkDeleteView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Delete multiple issues at once (workspace level)."""

    def perform_action(self):
        selected_queryset = self.get_selected_queryset()
        selected_count = selected_queryset.count()
        # Collect all issue IDs (selected + descendants) for subtask cleanup
        selected_ids = list(selected_queryset.values_list("pk", flat=True))
        descendant_ids = []
        for issue in selected_queryset:
            descendant_ids.extend(issue.get_descendants().values_list("pk", flat=True))
        all_ids = selected_ids + descendant_ids
        delete_subtasks_for_issue_ids(all_ids)
        selected_queryset.delete()
        messages.success(
            self.request,
            _("%(count)d issue(s) deleted successfully.") % {"count": selected_count},
        )
        remaining_count = self.get_queryset().work_items().search(self.form.cleaned_data["search"]).count()
        return calculate_valid_page(remaining_count, self.form.cleaned_data["page"])


class WorkspaceIssueBulkStatusView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the status of multiple issues at once (workspace level)."""

    def post(self, request, *args, **kwargs):
        self.status = request.POST.get("status")
        self._cascade_objects = []
        if self.status not in [choice[0] for choice in IssueStatus.choices]:
            messages.error(request, _("Invalid status value."))
            self.form = self.get_form()
            self.form.is_valid()
            return self.render_response(self.form.cleaned_data.get("page", 1))
        return super().post(request, *args, **kwargs)

    def perform_action(self):
        selected_qs = self.get_selected_queryset()
        status_choices = dict(IssueStatus.choices)
        objects = list(selected_qs.select_related("polymorphic_ctype"))
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in objects}
        new_display = status_choices.get(self.status, self.status)

        # Save objects snapshot before update for cascade check
        self._cascade_objects = objects

        updated_count = selected_qs.update(status=self.status)
        bulk_create_audit_logs(objects, "status", old_values, new_display, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d issue(s) updated to %(status)s.") % {"count": updated_count, "status": new_display},
        )
        return self.form.cleaned_data["page"]

    def render_response(self, page):
        response = super().render_response(page)
        if getattr(self, "_cascade_objects", None) and self.request.htmx:
            response = build_cascade_oob_response_bulk(self.request, self._cascade_objects, self.status, response)
        return response


class WorkspaceIssueBulkPriorityView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the priority of multiple issues at once (workspace level)."""

    def post(self, request, *args, **kwargs):
        self.priority = request.POST.get("priority")
        if self.priority not in [choice[0] for choice in IssuePriority.choices]:
            messages.error(request, _("Invalid priority value."))
            self.form = self.get_form()
            self.form.is_valid()
            return self.render_response(self.form.cleaned_data.get("page", 1))
        return super().post(request, *args, **kwargs)

    def perform_action(self):
        selected_qs = self.get_selected_queryset()
        priority_choices = dict(IssuePriority.choices)
        objects = list(selected_qs.select_related("polymorphic_ctype"))
        old_values = {obj.pk: priority_choices.get(obj.priority, obj.priority) for obj in objects}
        new_display = priority_choices.get(self.priority, self.priority)

        # priority lives on each concrete subclass, not on BaseIssue, so update each table
        selected_pks = [obj.pk for obj in objects]
        updated_count = 0
        for model_class in (Epic, Story, Bug, Chore):
            updated_count += model_class.objects.filter(pk__in=selected_pks).update(priority=self.priority)

        bulk_create_audit_logs(objects, "priority", old_values, new_display, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d issue(s) updated to %(priority)s.") % {"count": updated_count, "priority": new_display},
        )
        return self.form.cleaned_data["page"]


class WorkspaceIssueBulkRemoveFromSprintView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Remove multiple issues from a sprint at once (workspace level)."""

    def perform_action(self):
        selected_pks = list(self.get_selected_queryset().values_list("pk", flat=True))
        # sprint lives on each concrete work item subclass, not on BaseIssue
        removed_count = 0
        all_objects = []
        all_old_values = {}
        for model_class in (Story, Bug, Chore):
            qs = model_class.objects.filter(pk__in=selected_pks).exclude(sprint=None).select_related("sprint")
            objects = list(qs)
            all_objects.extend(objects)
            all_old_values.update({obj.pk: str(obj.sprint) for obj in objects})
            removed_count += qs.update(sprint=None)

        bulk_create_audit_logs(all_objects, "sprint", all_old_values, None, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d issue(s) removed from sprint.") % {"count": removed_count},
        )
        return self.form.cleaned_data["page"]


class WorkspaceIssueBulkAddToSprintView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Add multiple issues to a sprint at once (workspace level)."""

    def post(self, request, *args, **kwargs):
        self.sprint_key = request.POST.get("sprint", "").strip()
        if not self.sprint_key:
            messages.error(request, _("No sprint selected."))
            self.form = self.get_form()
            self.form.is_valid()
            return self.render_response(self.form.cleaned_data.get("page", 1))

        self.sprint = (
            Sprint.objects.for_workspace(self.workspace)
            .filter(
                status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE],
                key=self.sprint_key,
            )
            .first()
        )
        if not self.sprint:
            messages.error(request, _("Invalid sprint."))
            self.form = self.get_form()
            self.form.is_valid()
            return self.render_response(self.form.cleaned_data.get("page", 1))

        return super().post(request, *args, **kwargs)

    def perform_action(self):
        selected_pks = list(self.get_selected_queryset().values_list("pk", flat=True))
        new_display = str(self.sprint)
        # sprint lives on each concrete work item subclass, not on BaseIssue
        updated_count = 0
        all_objects = []
        all_old_values = {}
        for model_class in (Story, Bug, Chore):
            qs = model_class.objects.filter(pk__in=selected_pks).select_related("sprint")
            objects = list(qs)
            all_objects.extend(objects)
            all_old_values.update({obj.pk: str(obj.sprint) if obj.sprint else None for obj in objects})
            updated_count += qs.update(sprint=self.sprint)

        bulk_create_audit_logs(all_objects, "sprint", all_old_values, new_display, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d issue(s) added to %(sprint)s.") % {"count": updated_count, "sprint": self.sprint.name},
        )
        return self.form.cleaned_data["page"]


class WorkspaceIssueBulkAssigneeView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the assignee of multiple issues at once (workspace level)."""

    form_class = WorkspaceBulkAssigneeForm

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "queryset": self.get_queryset(),
            "workspace": self.workspace,
            "workspace_members": self.request.workspace_members,
        }

    def perform_action(self):
        assignee = self.form.cleaned_data["assignee"]
        selected_qs = self.get_selected_queryset()
        objects = list(selected_qs.select_related("polymorphic_ctype", "assignee"))
        old_values = {obj.pk: obj.assignee.get_display_name() if obj.assignee else None for obj in objects}
        new_display = assignee.get_display_name() if assignee else None

        updated_count = selected_qs.update(assignee=assignee)
        bulk_create_audit_logs(objects, "assignee", old_values, new_display, actor=self.request.user)

        if assignee:
            messages.success(
                self.request,
                _("%(count)d issue(s) assigned to %(assignee)s.") % {"count": updated_count, "assignee": new_display},
            )
        else:
            messages.success(
                self.request,
                _("%(count)d issue(s) unassigned.") % {"count": updated_count},
            )
        return self.form.cleaned_data["page"]


class WorkspaceIssueBulkMilestoneView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the milestone of multiple epics at once (workspace level)."""

    form_class = WorkspaceBulkMilestoneForm

    def get_form_kwargs(self):
        project_key = self.request.POST.get("project_filter", "")
        self._project = None
        if project_key:
            self._project = Project.objects.for_workspace(self.workspace).filter(key=project_key).first()
        return {
            "data": self.request.POST,
            "queryset": self.get_queryset(),
            "project": self._project,
        }

    def perform_action(self):
        milestone = self.form.cleaned_data["milestone"]
        selected_qs = self.get_selected_queryset()
        selected_pks = list(selected_qs.values_list("pk", flat=True))

        # milestone is Epic-only, so query Epic directly for audit log data
        epic_qs = Epic.objects.filter(pk__in=selected_pks).select_related("polymorphic_ctype", "milestone")
        objects = list(epic_qs)
        old_values = {obj.pk: str(obj.milestone) if obj.milestone else None for obj in objects}
        new_display = str(milestone) if milestone else None

        updated_count = Epic.objects.filter(pk__in=selected_pks).move_to_milestone(milestone)
        bulk_create_audit_logs(objects, "milestone", old_values, new_display, actor=self.request.user)

        if milestone:
            messages.success(
                self.request,
                _("%(count)d epic(s) moved to %(milestone)s.") % {"count": updated_count, "milestone": milestone.title},
            )
        else:
            messages.success(
                self.request,
                _("%(count)d epic(s) removed from milestone.") % {"count": updated_count},
            )
        return self.form.cleaned_data["page"]


class WorkspaceIssueBulkDeletePreviewView(WorkspaceBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Preview cascade impact before bulk-deleting issues."""

    def post(self, request, *args, **kwargs):
        self.form = self.get_form()
        if not self.form.is_valid() or not self.form.cleaned_data.get("issues"):
            return render(
                request,
                "issues/includes/bulk_delete_confirm_content.html",
                {
                    "selected_count": 0,
                    "descendant_count": 0,
                    "subtask_count": 0,
                },
            )

        selected_queryset = self.get_selected_queryset()
        selected_keys = list(selected_queryset.values_list("key", flat=True))
        selected_count = len(selected_keys)

        # Compute cascade counts
        selected_ids = list(selected_queryset.values_list("pk", flat=True))
        descendant_ids = []
        for issue in selected_queryset:
            descendant_ids.extend(issue.get_descendants().values_list("pk", flat=True))
        descendant_count = len(descendant_ids)
        all_ids = selected_ids + descendant_ids
        subtask_count = count_subtasks_for_issue_ids(all_ids)

        # Determine context: embed type, checkbox name, hx-target, hx-indicator
        embed_value = request.POST.get("embed", "")
        is_project_epics_embed = embed_value == "project_epics"

        if is_project_epics_embed:
            checkbox_name = "epics"
            hx_target = "#epics-embed"
            hx_indicator = "#embed-list-loading"
        elif embed_value:
            checkbox_name = "issues"
            hx_target = "#issues-embed"
            hx_indicator = "#embed-list-loading"
        else:
            checkbox_name = "issues"
            hx_target = "#page-content"
            hx_indicator = "#list-loading"

        # Build passthrough fields for the actual delete POST
        passthrough_fields = {}
        for field_name in [
            "page",
            "search",
            "status_filter",
            "type_filter",
            "assignee_filter",
            "group_by",
            "project_filter",
            "sprint_filter",
            "epic_filter",
            "milestone_filter",
            "priority_filter",
            "embed",
        ]:
            value = request.POST.get(field_name, "")
            if value:
                passthrough_fields[field_name] = value

        delete_url = reverse(
            "workspace_issues_bulk_delete",
            kwargs={"workspace_slug": kwargs["workspace_slug"]},
        )

        return render(
            request,
            "issues/includes/bulk_delete_confirm_content.html",
            {
                "selected_count": selected_count,
                "descendant_count": descendant_count,
                "subtask_count": subtask_count,
                "selected_keys": selected_keys,
                "checkbox_name": checkbox_name,
                "delete_url": delete_url,
                "hx_target": hx_target,
                "hx_indicator": hx_indicator,
                "passthrough_fields": passthrough_fields,
            },
        )
