from collections import OrderedDict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.issues.cascade import build_cascade_oob_response
from apps.issues.forms import EpicForm, MilestoneForm, get_form_class_for_type
from apps.issues.helpers import (
    annotate_epic_child_counts,
    build_grouped_epics_by_milestone,
    build_grouped_issues,
    calculate_progress,
    count_subtasks_for_issue_ids,
    delete_subtasks_for_issue_ids,
    get_epic_content_type_id,
)
from apps.issues.models import BaseIssue, Epic, IssuePriority, IssueStatus, Milestone
from apps.issues.views.mixins import ISSUE_TYPE_CHOICES, WORK_ITEM_TYPE_CHOICES, IssueListContextMixin
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.filters import build_filter_section, count_active_filters, get_status_filter_label, parse_status_filter
from apps.workspaces.limits import LimitExceededError, check_work_item_limit
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin
from apps.workspaces.models import Workspace

from ..models import Project, ProjectStatus
from ..tasks import move_project_task
from .mixins import ProjectFormMixin, ProjectSingleObjectMixin, ProjectViewMixin

User = get_user_model()

GROUP_BY_CHOICES = [
    ("status", _("Status")),
    ("lead", _("Lead")),
]


def _attach_progress_to_projects(projects):
    """Batch-compute progress for a list of projects, avoiding N+1 queries.

    Fetches all work items (excludes epics) for the given projects in one query,
    then attaches a progress dict to each project object.
    """
    project_ids = [p.pk for p in projects]
    if not project_ids:
        return

    children_by_project = {}
    all_children = (
        BaseIssue.objects.filter(project_id__in=project_ids)
        .exclude(polymorphic_ctype_id=get_epic_content_type_id())
        .non_polymorphic()
        .only("status", "estimated_points", "project_id")
    )
    for child in all_children:
        children_by_project.setdefault(child.project_id, []).append(child)

    for project in projects:
        project.progress = calculate_progress(children_by_project.get(project.pk, []))


class ProjectListView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ListView):
    """List all projects in a workspace with pagination."""

    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.lead_filter = self.request.GET.get("lead", "").strip()
        self.group_by = self.request.GET.get("group_by", "").strip()
        queryset = (
            Project.objects.for_workspace(self.workspace).search(self.search_query).select_related("lead", "workspace")
        )
        status_values = parse_status_filter(self.status_filter, ProjectStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)
        if self.lead_filter:
            if self.lead_filter == "none":
                queryset = queryset.filter(lead__isnull=True)
            elif self.lead_filter.isdigit():
                queryset = queryset.filter(lead_id=int(self.lead_filter))
        # Apply ordering based on grouping
        if self.group_by == "status":
            queryset = queryset.order_by("status", "name")
        elif self.group_by == "lead":
            queryset = queryset.order_by("lead__first_name", "lead__last_name", "name")
        return queryset

    def get_paginate_by(self, queryset):
        if self.group_by:
            return None  # No pagination when grouped
        return self.paginate_by

    def _get_lead_filter_label(self):
        if not self.lead_filter:
            return ""
        if self.lead_filter == "none":
            return _("No lead")
        if self.lead_filter.isdigit():
            lead_id = int(self.lead_filter)
            for member in self.request.workspace_members:
                if member.pk == lead_id:
                    return member.get_display_name()
        return ""

    def _get_group_by_label(self):
        if not self.group_by:
            return ""
        return dict(GROUP_BY_CHOICES).get(self.group_by, "")

    def _build_grouped_projects(self, projects):
        """Build a dictionary of projects grouped by the selected field."""
        grouped = OrderedDict()
        if self.group_by == "status":
            status_labels = dict(ProjectStatus.choices)
            for project in projects:
                group_name = status_labels.get(project.status, project.status)
                if group_name not in grouped:
                    grouped[group_name] = []
                grouped[group_name].append(project)
        elif self.group_by == "lead":
            for project in projects:
                group_name = project.lead.get_display_name() if project.lead else str(_("No lead"))
                if group_name not in grouped:
                    grouped[group_name] = []
                grouped[group_name].append(project)
        return grouped

    def get_template_names(self):
        if self.request.htmx:
            target = self.request.htmx.target
            if target == "list-content":
                return [f"{self.template_name}#list-content"]
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Build lead choices from workspace members
        lead_choices = [("none", _("No lead"))]
        for member in self.request.workspace_members:
            lead_choices.append((str(member.pk), member.get_display_name()))

        # Build filter sections for modal
        filter_sections = [
            build_filter_section(
                name="status",
                label=_("Status"),
                filter_type="multi_select",
                choices=ProjectStatus.choices,
                current_value=self.status_filter,
            ),
            build_filter_section(
                name="lead",
                label=_("Lead"),
                filter_type="single_select",
                choices=lead_choices,
                current_value=self.lead_filter,
                empty_label=_("All"),
            ),
            build_filter_section(
                name="group_by",
                label=_("Group by"),
                filter_type="single_select",
                choices=GROUP_BY_CHOICES,
                current_value=self.group_by,
                empty_label=_("None"),
            ),
        ]

        # Count active filters (excluding group_by as it's not really a filter)
        active_filters = {"status": self.status_filter, "lead": self.lead_filter}
        active_filter_count = count_active_filters(active_filters)

        context["page_title"] = _("Projects")
        context["status_choices"] = ProjectStatus.choices
        context["workspace_members"] = self.request.workspace_members
        context["search_query"] = self.search_query
        context["move_target_workspaces"] = Workspace.objects.for_user(self.request.user).exclude(pk=self.workspace.pk)
        context["status_filter"] = self.status_filter
        context["status_filter_label"] = get_status_filter_label(self.status_filter, ProjectStatus.choices)
        context["lead_filter"] = self.lead_filter
        context["lead_filter_label"] = self._get_lead_filter_label()
        context["group_by"] = self.group_by
        context["group_by_label"] = self._get_group_by_label()
        context["group_by_choices"] = GROUP_BY_CHOICES
        context["filter_sections"] = filter_sections
        context["active_filter_count"] = active_filter_count

        projects = list(context["projects"])
        _attach_progress_to_projects(projects)
        if self.group_by:
            context["grouped_projects"] = self._build_grouped_projects(projects)
        if context.get("is_paginated"):
            context["elided_page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )
        return context


class ProjectDetailView(
    LoginAndWorkspaceRequiredMixin,
    ProjectViewMixin,
    ProjectSingleObjectMixin,
    DetailView,
):
    """Display project details."""

    template_name = "projects/project_detail.html"

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace).select_related("lead", "workspace")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Track project exploration for onboarding (visiting any project detail page counts)
        if not request.user.onboarding_progress.get("demo_explored"):
            request.user.onboarding_progress["demo_explored"] = True
            request.user.save(update_fields=["onboarding_progress"])
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"{self.object.name} Roadmap"
        work_items = (
            BaseIssue.objects.filter(project=self.object)
            .exclude(polymorphic_ctype_id=get_epic_content_type_id())
            .non_polymorphic()
            .only("status", "estimated_points")
        )
        context["progress"] = calculate_progress(work_items)
        context["move_target_workspaces"] = Workspace.objects.for_user(self.request.user).exclude(pk=self.workspace.pk)
        return context


class ProjectCreateView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ProjectFormMixin, CreateView):
    """Create a new project."""

    template_name = "projects/project_form.html"

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["projects/includes/project_form_modal.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("New Project")
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workspace = self.workspace
        self.object.created_by = self.request.user
        self.object.save()
        messages.success(self.request, _("Project created successfully."))

        if self.is_modal():
            list_url = reverse("projects:project_list", kwargs={"workspace_slug": self.workspace.slug})
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('project-created', "
                "{ detail: { listUrl: '" + list_url + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.object.get_absolute_url())


class ProjectUpdateView(
    LoginAndWorkspaceRequiredMixin,
    ProjectViewMixin,
    ProjectSingleObjectMixin,
    ProjectFormMixin,
    UpdateView,
):
    """Update an existing project."""

    template_name = "projects/project_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Edit %s") % self.object.name
        return context

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace).select_related("lead")

    def form_valid(self, form):
        messages.success(self.request, _("Project updated successfully."))
        return super().form_valid(form)


class ProjectDeleteView(
    LoginAndWorkspaceRequiredMixin,
    ProjectViewMixin,
    ProjectSingleObjectMixin,
    DeleteView,
):
    """Delete a project."""

    template_name = "projects/project_confirm_delete.html"

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace)

    def get_template_names(self):
        if self.request.htmx:
            return ["projects/includes/delete_confirm_content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        context["page_title"] = _("Delete %s") % project.name
        context["milestone_count"] = Milestone.objects.for_project(project).count()
        context["epic_count"] = Epic.objects.for_project(project).count()
        # Work items = all non-epic issues
        work_item_ids = list(
            BaseIssue.objects.for_project(project)
            .exclude(polymorphic_ctype_id=get_epic_content_type_id())
            .values_list("pk", flat=True)
        )
        context["work_item_count"] = len(work_item_ids)
        context["subtask_count"] = count_subtasks_for_issue_ids(work_item_ids)
        return context

    def get_success_url(self):
        return reverse(
            "projects:project_list",
            kwargs={"workspace_slug": self.kwargs["workspace_slug"]},
        )

    def form_valid(self, form):
        # Delete subtasks before project deletion (GenericFK won't cascade)
        work_item_ids = list(
            BaseIssue.objects.for_project(self.object)
            .exclude(polymorphic_ctype_id=get_epic_content_type_id())
            .values_list("pk", flat=True)
        )
        delete_subtasks_for_issue_ids(work_item_ids)
        messages.success(self.request, _("Project deleted successfully."))
        return super().form_valid(form)


class ProjectCloneView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, View):
    """Clone an existing project."""

    def post(self, request, *args, **kwargs):
        original = get_object_or_404(Project.objects.for_workspace(self.workspace), key=kwargs["key"])
        cloned = Project.objects.create(
            workspace=original.workspace,
            name=_("%(name)s (Copy)") % {"name": original.name},
            description=original.description,
            status=original.status,
            lead=original.lead,
            created_by=request.user,
        )
        messages.success(request, _("Project cloned successfully."))
        return redirect(cloned.get_absolute_url())


# ============================================================================
# Project inline editing
# ============================================================================


class ProjectRowInlineEditView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, View):
    """Handle inline editing of project rows in list views."""

    def _get_context(self, request, project, form=None):
        """Build common context for GET/POST handlers."""
        # Determine which columns to show (default to all for standalone usage)
        show_status = request.GET.get("show_status", "1") != "0"
        show_lead = request.GET.get("show_lead", "1") != "0"

        # Derive group_by from show_* params (for project_row.html template)
        group_by = ""
        if not show_status:
            group_by = "status"
        elif not show_lead:
            group_by = "lead"

        context = {
            "project": project,
            "workspace": self.workspace,
            "workspace_members": request.workspace_members,
            "status_choices": ProjectStatus.choices,
            "show_status": show_status,
            "show_lead": show_lead,
            "group_by": group_by,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the project row."""
        from ..forms import ProjectRowInlineEditForm

        project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("lead"),
            key=kwargs["key"],
        )
        context = self._get_context(request, project)

        display_template = "projects/includes/project_row.html"
        edit_template = "projects/includes/project_row_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = ProjectRowInlineEditForm(
            initial={
                "name": project.name,
                "status": project.status,
                "lead": project.lead,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        from ..forms import ProjectRowInlineEditForm

        project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("lead"),
            key=kwargs["key"],
        )
        form = ProjectRowInlineEditForm(request.POST, workspace_members=request.workspace_members)
        context = self._get_context(request, project, form)

        display_template = "projects/includes/project_row.html"
        edit_template = "projects/includes/project_row_edit.html"

        if form.is_valid():
            old_status = project.status

            # Update project fields
            project.name = form.cleaned_data["name"]
            project.status = form.cleaned_data["status"]
            project.lead = form.cleaned_data.get("lead")
            project.save()

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, project, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


class ProjectDetailInlineEditView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, View):
    """Handle inline editing of project details on the detail page."""

    def _get_context(self, request, project, form=None):
        """Build common context for GET/POST handlers."""
        context = {
            "project": project,
            "workspace": self.workspace,
            "workspace_members": request.workspace_members,
            "status_choices": ProjectStatus.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the project detail header."""
        from ..forms import ProjectDetailInlineEditForm

        project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("lead"),
            key=kwargs["key"],
        )
        context = self._get_context(request, project)

        display_template = "projects/includes/project_detail_header.html"
        edit_template = "projects/includes/project_detail_header_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = ProjectDetailInlineEditForm(
            initial={
                "name": project.name,
                "description": project.description,
                "status": project.status,
                "lead": project.lead,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        from ..forms import ProjectDetailInlineEditForm

        project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("lead"),
            key=kwargs["key"],
        )
        form = ProjectDetailInlineEditForm(
            request.POST,
            workspace_members=request.workspace_members,
        )
        context = self._get_context(request, project, form)

        display_template = "projects/includes/project_detail_header.html"
        edit_template = "projects/includes/project_detail_header_edit.html"

        if form.is_valid():
            old_status = project.status

            # Update project fields
            project.name = form.cleaned_data["name"]
            project.description = form.cleaned_data.get("description") or ""
            project.status = form.cleaned_data["status"]
            project.lead = form.cleaned_data.get("lead")
            project.save()

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, project, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


# ============================================================================
# Project Epics Embed Views (for Milestones tab)
# ============================================================================


EPIC_GROUP_BY_CHOICES = [
    ("status", _("Status")),
    ("priority", _("Priority")),
    ("assignee", _("Assignee")),
]


class ProjectEpicsEmbedView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ProjectSingleObjectMixin, ListView):
    """Embedded epics list for project detail page. Shows epics grouped by milestone."""

    template_name = "projects/project_epics_embed.html"
    context_object_name = "epics"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.priority_filter = self.request.GET.get("priority", "").strip()
        self.assignee_filter = self.request.GET.get("assignee", "").strip()
        self.milestone_filter = self.request.GET.get("milestone", "").strip()

        queryset = Epic.objects.for_project(self.project).select_related(
            "project", "project__workspace", "assignee", "milestone"
        )

        # Apply search filter
        if self.search_query:
            queryset = queryset.search(self.search_query)

        # Apply status filter
        status_values = parse_status_filter(self.status_filter, IssueStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)

        # Apply priority filter
        if self.priority_filter:
            priority_values = parse_status_filter(self.priority_filter, IssuePriority.choices)
            if priority_values:
                queryset = queryset.filter(priority__in=priority_values)

        # Apply assignee filter
        if self.assignee_filter:
            if self.assignee_filter == "none":
                queryset = queryset.filter(assignee__isnull=True)
            elif self.assignee_filter.isdigit():
                queryset = queryset.filter(assignee_id=int(self.assignee_filter))

        # Apply milestone filter
        if self.milestone_filter:
            if self.milestone_filter == "none":
                queryset = queryset.filter(milestone__isnull=True)
            else:
                queryset = queryset.filter(milestone__key=self.milestone_filter)

        return queryset.order_by("key")

    def get_template_names(self):
        if self.request.htmx:
            target = self.request.htmx.target
            if target == "epics-list":
                return [f"{self.template_name}#list-content"]
            elif target == "epics-embed":
                return [f"{self.template_name}#embed-content"]
        return [self.template_name]

    def _get_assignee_filter_label(self):
        if not self.assignee_filter:
            return ""
        if self.assignee_filter == "none":
            return _("Unassigned")
        if self.assignee_filter.isdigit():
            assignee_id = int(self.assignee_filter)
            for member in self.request.workspace_members:
                if member.pk == assignee_id:
                    return member.get_display_name()
        return ""

    def _get_milestone_filter_label(self):
        if not self.milestone_filter:
            return ""
        if self.milestone_filter == "none":
            return _("No Milestone")
        milestone = Milestone.objects.for_project(self.project).filter(key=self.milestone_filter).first()
        if milestone:
            return f"[{milestone.key}] {milestone.title}"
        return ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["embed_url"] = reverse(
            "projects:project_epics_embed",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
                "key": self.project.key,
            },
        )
        context["workspace_members"] = self.request.workspace_members
        context["search_query"] = self.search_query
        context["status_filter"] = self.status_filter
        context["status_filter_label"] = get_status_filter_label(self.status_filter, IssueStatus.choices)
        context["priority_filter"] = self.priority_filter
        context["priority_filter_label"] = get_status_filter_label(self.priority_filter, IssuePriority.choices)
        context["assignee_filter"] = self.assignee_filter
        context["assignee_filter_label"] = self._get_assignee_filter_label()
        context["milestone_filter"] = self.milestone_filter
        context["milestone_filter_label"] = self._get_milestone_filter_label()
        context["status_choices"] = IssueStatus.choices
        context["priority_choices"] = IssuePriority.choices

        # Build assignee choices
        assignee_choices = [("none", _("Unassigned"))]
        for member in self.request.workspace_members:
            assignee_choices.append((str(member.pk), member.get_display_name()))
        context["assignee_choices"] = assignee_choices

        # Build milestone choices
        milestones = Milestone.objects.for_project(self.project).order_by("key")
        milestone_choices = [("none", _("No Milestone"))]
        for m in milestones:
            milestone_choices.append((m.key, f"[{m.key}] {m.title}"))
        context["milestone_choices"] = milestone_choices

        # Build filter sections for modal
        filter_sections = [
            build_filter_section(
                name="status",
                label=_("Status"),
                filter_type="multi_select",
                choices=IssueStatus.choices,
                current_value=self.status_filter,
            ),
            build_filter_section(
                name="priority",
                label=_("Priority"),
                filter_type="multi_select",
                choices=IssuePriority.choices,
                current_value=self.priority_filter,
            ),
            build_filter_section(
                name="assignee",
                label=_("Assignee"),
                filter_type="single_select",
                choices=assignee_choices,
                current_value=self.assignee_filter,
                empty_label=_("All"),
            ),
            build_filter_section(
                name="milestone",
                label=_("Milestone"),
                filter_type="single_select",
                choices=milestone_choices,
                current_value=self.milestone_filter,
                empty_label=_("All"),
            ),
        ]
        context["filter_sections"] = filter_sections

        # Total epic count (unfiltered) for showing/hiding search and filters UI
        context["total_epic_count"] = Epic.objects.for_project(self.project).count()

        # Count active filters
        active_filters = {
            "status": self.status_filter,
            "priority": self.priority_filter,
            "assignee": self.assignee_filter,
            "milestone": self.milestone_filter,
        }
        context["active_filter_count"] = count_active_filters(active_filters)

        # Build grouped epics by milestone
        # Only include empty milestone groups when there are no active filters
        has_active_filters = bool(
            self.search_query
            or self.status_filter
            or self.priority_filter
            or self.assignee_filter
            or self.milestone_filter
        )
        context["grouped_epics"] = build_grouped_epics_by_milestone(
            context["epics"],
            project=self.project,
            include_empty_milestones=not has_active_filters,
        )

        # Annotate epic child counts for expand/collapse UI
        all_epics = [epic for group in context["grouped_epics"] for epic in group["epics"]]
        annotate_epic_child_counts(all_epics)

        context["project_milestones"] = Milestone.objects.for_project(self.project).for_choices()

        return context


class ProjectOrphanIssuesEmbedView(
    LoginAndWorkspaceRequiredMixin,
    IssueListContextMixin,
    ProjectViewMixin,
    ProjectSingleObjectMixin,
    ListView,
):
    """Embedded full-featured issues list for orphan work items on the project detail page.

    Shows root-level work items (stories, bugs, chores) with no parent epic,
    with filtering, grouping (including due_date), sorting, and bulk actions.
    """

    template_name = "issues/issues_embed.html"
    context_object_name = "issues"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.type_filter = self.request.GET.get("type", "").strip()
        self.assignee_filter = self.request.GET.get("assignee", "").strip()
        self.sprint_filter = self.request.GET.get("sprint", "").strip()
        self.priority_filter = self.request.GET.get("priority", "").strip()
        self.group_by = self.request.GET.get("group_by", "").strip()
        self.sort_by = self.request.GET.get("sort_by", "").strip() if not self.group_by else ""

        queryset = (
            BaseIssue.objects.for_project(self.project)
            .roots()
            .work_items()
            .select_related("project", "project__workspace", "assignee", "polymorphic_ctype")
        )

        queryset = self.apply_issue_filters(
            queryset,
            self.type_filter,
            self.search_query,
            self.status_filter,
            self.assignee_filter,
            self.sprint_filter,
            priority_filter=self.priority_filter,
        )
        queryset = self.apply_issue_ordering(queryset, self.group_by, self.sort_by)
        return queryset

    def get_paginate_by(self, queryset):
        if self.group_by:
            return None
        return self.paginate_by

    def get_template_names(self):
        if self.request.htmx:
            target = self.request.htmx.target
            if target == "issues-list":
                return [f"{self.template_name}#list-content"]
            elif target == "issues-embed":
                return [f"{self.template_name}#embed-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["project_orphan"] = True
        context["embed_modal_prefix"] = "orphan-"
        context["embed_url"] = reverse(
            "projects:project_orphan_issues_embed",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
                "key": self.project.key,
            },
        )
        context["workspace_members"] = self.request.workspace_members

        orphan_group_by_choices = [
            ("status", _("Status")),
            ("priority", _("Priority")),
            ("assignee", _("Assignee")),
            ("due_date", _("Due Date")),
        ]

        context.update(
            self.get_issue_list_context(
                self.search_query,
                self.status_filter,
                self.type_filter,
                self.assignee_filter,
                self.project.key,
                self.group_by,
                group_by_in_modal=False,
                sprint_filter=self.sprint_filter,
                include_sprint_filter=True,
                extra_group_by_choices=orphan_group_by_choices,
                exclude_epic_group_by=True,
                sort_by=self.sort_by,
                priority_filter=self.priority_filter,
                include_priority_filter=True,
                type_filter_type="multi_select",
                type_filter_choices=WORK_ITEM_TYPE_CHOICES,
            )
        )
        context["available_sprints"] = (
            Sprint.objects.for_workspace(self.workspace)
            .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
            .order_by("-status", "-start_date")
        )
        if self.group_by:
            context["grouped_issues"] = build_grouped_issues(context["issues"], self.group_by)
        if context.get("is_paginated"):
            context["elided_page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )
        return context


class ProjectEpicChildrenView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, View):
    """HTMX view for lazy-loading children of an epic in the project detail page."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )

    def get(self, request, *args, **kwargs):
        epic = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["epic_key"])
        children = epic.get_children_issues().select_related("project", "project__workspace", "assignee")
        context = {
            "children": children,
            "workspace": self.workspace,
            "project": self.project,
            "parent": epic,
        }
        return render(request, "projects/includes/epic_children_embed.html", context)


class ProjectEpicCreateView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ProjectSingleObjectMixin, View):
    """Create a new epic from the project detail page.

    The epic's project is automatically set. Milestone can be optionally selected.
    """

    template_name = "projects/epic_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )
        # Pre-select milestone if provided in query params
        milestone_key = request.GET.get("milestone")
        if milestone_key:
            self.milestone = Milestone.objects.for_project(self.project).filter(key=milestone_key).first()
        else:
            self.milestone = None

    def get_form_kwargs(self):
        kwargs = {
            "project": self.project,
            "workspace_members": self.request.workspace_members,
        }
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return kwargs

    def get_form(self):
        form = EpicForm(**self.get_form_kwargs())
        # Hide project field since it's preset
        if "project" in form.fields:
            del form.fields["project"]
        # Hide milestone field when pre-selected via query param
        if self.milestone and "milestone" in form.fields:
            del form.fields["milestone"]
        return form

    def get_context_data(self, **kwargs):
        context = {
            "workspace": self.workspace,
            "project": self.project,
            "milestone": self.milestone,
            "form": kwargs.get("form", self.get_form()),
            "issue_type_label": _("Epic"),
        }
        return context

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["projects/includes/epic_form_modal.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return render(request, self.get_template_names()[0], context)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.project = self.project
        if self.milestone:
            obj.milestone = self.milestone
        obj.created_by = self.request.user
        obj.key = obj._generate_unique_key()
        # Epics are root-level issues
        BaseIssue.add_root(instance=obj)

        messages.success(self.request, _("Epic created successfully."))

        # For modal submissions, close modal, reload epics list, and show toast
        if self.is_modal():
            embed_url = reverse(
                "projects:project_epics_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": self.project.key,
                },
            )
            # Render messages with out-of-band swap to show toast
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('epic-created', "
                "{ detail: { embedUrl: '" + embed_url + "', targetId: 'epics-embed' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.project.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class ProjectIssueCreateView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ProjectSingleObjectMixin, View):
    """Create a new work item (story, bug, chore, issue) from the project detail page.

    The item's project is automatically set. Epic parent is optional.
    """

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )
        self.issue_type = kwargs.get("issue_type", "story")
        # Pre-select epic parent if provided in query params
        epic_key = request.GET.get("epic") or request.POST.get("epic")
        if epic_key:
            self.epic = Epic.objects.for_project(self.project).filter(key=epic_key).first()
        else:
            self.epic = None

    def get_form_class(self):
        return get_form_class_for_type(self.issue_type)

    def get_form_kwargs(self):
        kwargs = {
            "project": self.project,
            "workspace_members": self.request.workspace_members,
        }
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return kwargs

    def get_form(self):
        form = self.get_form_class()(**self.get_form_kwargs())
        # Hide project field since it's preset
        if "project" in form.fields:
            del form.fields["project"]
        # Hide parent field when pre-selected via query param, or when creating from the orphan section
        if (self.epic or self.request.GET.get("embed") == "orphan") and "parent" in form.fields:
            del form.fields["parent"]
        return form

    def get_context_data(self, **kwargs):
        return {
            "workspace": self.workspace,
            "project": self.project,
            "epic": self.epic,
            "form": kwargs.get("form", self.get_form()),
            "issue_type": self.issue_type,
            "issue_type_label": dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue")),
        }

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["projects/includes/project_issue_create_form_modal.html"]
        if self.request.htmx:
            return ["issues/issue_form.html#page-content"]
        return ["issues/issue_form.html"]

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return render(request, self.get_template_names()[0], context)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        try:
            check_work_item_limit(self.workspace)
        except LimitExceededError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        obj = form.save(commit=False)
        obj.project = self.project
        obj.created_by = self.request.user
        obj.key = obj._generate_unique_key()

        # Use pre-selected epic or form-provided parent
        parent = self.epic or form.cleaned_data.get("parent")

        if parent:
            parent.add_child(instance=obj)
        else:
            BaseIssue.add_root(instance=obj)

        issue_type_label = dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue"))
        messages.success(
            self.request,
            _("%(type)s created successfully.") % {"type": issue_type_label},
        )

        if self.is_modal():
            if self.request.GET.get("embed") == "orphan":
                embed_url_name = "projects:project_orphan_issues_embed"
                target_id = "issues-embed"
            else:
                embed_url_name = "projects:project_epics_embed"
                target_id = "epics-embed"
            embed_url = reverse(
                embed_url_name,
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": self.project.key,
                },
            )
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('issue-created', "
                "{ detail: { embedUrl: '" + embed_url + "', targetId: '" + target_id + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(obj.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class ProjectMilestoneCreateView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, ProjectSingleObjectMixin, View):
    """Create a new milestone from the project detail page.

    The milestone's project is automatically set.
    """

    template_name = "issues/milestones/milestone_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["key"],
        )

    def get_form_kwargs(self):
        kwargs = {
            "project": self.project,
            "workspace_members": self.request.workspace_members,
        }
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return kwargs

    def get_form(self):
        return MilestoneForm(**self.get_form_kwargs())

    def get_context_data(self, **kwargs):
        return {
            "workspace": self.workspace,
            "project": self.project,
            "form": kwargs.get("form", self.get_form()),
        }

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["projects/includes/milestone_form_modal.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get(self, request, *args, **kwargs):
        context = self.get_context_data()
        return render(request, self.get_template_names()[0], context)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.project = self.project
        obj.created_by = self.request.user
        obj.save()

        messages.success(self.request, _("Milestone created successfully."))

        if self.is_modal():
            embed_url = reverse(
                "projects:project_epics_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "key": self.project.key,
                },
            )
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('milestone-created', "
                "{ detail: { embedUrl: '" + embed_url + "', targetId: 'epics-embed' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.project.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class ProjectMoveView(LoginAndWorkspaceRequiredMixin, ProjectViewMixin, View):
    """Move a single project to another workspace (POST only)."""

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        project = get_object_or_404(
            Project.objects.for_workspace(self.workspace),
            key=kwargs["key"],
        )
        target_workspace_pk = request.POST.get("workspace")
        target_workspace = get_object_or_404(
            Workspace.objects.for_user(request.user).exclude(pk=self.workspace.pk),
            pk=target_workspace_pk,
        )
        move_project_task.delay(project.pk, target_workspace.pk)
        messages.success(
            request,
            _("Project %(key)s is being moved to %(workspace)s.")
            % {"key": project.key, "workspace": target_workspace.name},
        )
        return redirect(reverse("projects:project_list", kwargs={"workspace_slug": self.kwargs["workspace_slug"]}))
