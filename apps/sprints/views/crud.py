from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.issues.helpers import build_grouped_issues, build_progress_dict, calculate_progress
from apps.issues.models import BaseIssue, Bug, Chore, Story
from apps.issues.views.mixins import IssueListContextMixin
from apps.sprints.forms import SprintDetailInlineEditForm, SprintForm, SprintRowInlineEditForm
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.views.mixins import SprintFormMixin, SprintListContextMixin, SprintSingleObjectMixin, SprintViewMixin
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin


class SprintListView(SprintViewMixin, SprintListContextMixin, LoginAndWorkspaceRequiredMixin, ListView):
    """List all sprints in a workspace with filtering and pagination."""

    template_name = "sprints/sprint_list.html"
    context_object_name = "sprints"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    # Default filter to show only planning and active sprints
    DEFAULT_STATUS_FILTER = "planning,active"

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        raw_status_filter = self.request.GET.get("status", None)
        self.owner_filter = self.request.GET.get("owner", "").strip()

        # Apply default status filter unless explicitly set (including "all" to show everything)
        if raw_status_filter is None:
            self.status_filter = self.DEFAULT_STATUS_FILTER
            self.using_default_status_filter = True
        elif raw_status_filter == "all":
            self.status_filter = ""
            self.using_default_status_filter = False
        else:
            self.status_filter = raw_status_filter.strip()
            self.using_default_status_filter = False

        queryset = Sprint.objects.for_workspace(self.workspace).select_related("workspace", "owner").with_progress()
        return self.apply_sprint_filters(queryset, self.search_query, self.status_filter, self.owner_filter)

    def get_template_names(self):
        if self.request.htmx and not self.request.htmx.history_restore_request:
            target = self.request.htmx.target
            if target == "list-content":
                return [f"{self.template_name}#list-content"]
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Sprints")
        context.update(
            self.get_sprint_list_context(
                self.search_query,
                self.status_filter,
                self.owner_filter,
                using_default_status_filter=self.using_default_status_filter,
            )
        )

        if context.get("is_paginated"):
            context["elided_page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )

        # Build progress dicts from the annotated weights
        for sprint in context["sprints"]:
            total = getattr(sprint, "progress_total_weight", 0)
            if total:
                done = getattr(sprint, "progress_done_weight", 0)
                in_progress = getattr(sprint, "progress_in_progress_weight", 0)
                sprint.progress = build_progress_dict(done, in_progress, total - done - in_progress)
            else:
                sprint.progress = None

        return context


class SprintDetailView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, DetailView):
    """Display sprint details."""

    template_name = "sprints/sprint_detail.html"

    def get_queryset(self):
        return Sprint.objects.for_workspace(self.workspace).select_related("workspace", "owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.object
        context["page_title"] = sprint.name

        # For active sprints, compute completed_points in real-time
        if sprint.status == SprintStatus.ACTIVE:
            sprint.completed_points = sprint.calculate_completed_points()

        # Get all work items in this sprint
        work_items = self._get_sprint_work_items()

        # Calculate progress
        context["progress"] = calculate_progress(work_items)

        # Count items
        context["item_count"] = len(work_items)

        # Calculate total points from work items
        context["total_points"] = sum(item.estimated_points or 0 for item in work_items)

        return context

    def _get_sprint_work_items(self):
        """Get all work items assigned to this sprint."""
        sprint = self.object
        work_items = []

        for model in [Story, Bug, Chore]:
            items = model.objects.filter(sprint=sprint).select_related("project", "assignee")
            work_items.extend(items)

        return work_items


class SprintCreateView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintFormMixin, CreateView):
    """Create a new sprint."""

    template_name = "sprints/sprint_form.html"
    form_class = SprintForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("New Sprint")
        return context

    def get_initial(self):
        initial = super().get_initial()

        # Find the latest completed sprint to base dates on
        latest_completed = Sprint.objects.for_workspace(self.workspace).completed().order_by("-end_date").first()

        if latest_completed:
            # Start date is the end date of the latest completed sprint
            initial["start_date"] = latest_completed.end_date
            # End date is start date + 7 days
            initial["end_date"] = latest_completed.end_date + timedelta(days=7)

        return initial

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workspace = self.workspace
        self.object.created_by = self.request.user
        self.object.save()

        messages.success(self.request, _("Sprint created successfully."))
        return redirect(self.object.get_absolute_url())


class SprintUpdateView(
    SprintViewMixin,
    LoginAndWorkspaceRequiredMixin,
    SprintSingleObjectMixin,
    SprintFormMixin,
    UpdateView,
):
    """Update an existing sprint."""

    template_name = "sprints/sprint_form.html"
    form_class = SprintForm

    def get_queryset(self):
        return Sprint.objects.for_workspace(self.workspace)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Edit %s") % self.object.name
        return context

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Sprint updated successfully."))
        return redirect(self.object.get_absolute_url())


class SprintDeleteView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, DeleteView):
    """Delete a sprint."""

    template_name = "sprints/sprint_confirm_delete.html"

    def get_queryset(self):
        return Sprint.objects.for_workspace(self.workspace)

    def get_template_names(self):
        if self.request.htmx and not self.request.htmx.history_restore_request:
            return ["sprints/includes/delete_confirm_content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Delete %s") % self.object.name
        # Count items assigned to this sprint
        item_count = 0
        for model in [Story, Bug, Chore]:
            item_count += model.objects.filter(sprint=self.object).count()
        context["item_count"] = item_count
        return context

    def get_success_url(self):
        return reverse(
            "sprints:sprint_list",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
            },
        )

    def form_valid(self, form):
        messages.success(self.request, _("Sprint deleted successfully."))
        return super().form_valid(form)


class SprintIssueListEmbedView(SprintViewMixin, IssueListContextMixin, LoginAndWorkspaceRequiredMixin, ListView):
    """Embedded issue list for sprint detail page (lazy-loaded via HTMX)."""

    template_name = "issues/issues_embed.html"
    context_object_name = "issues"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.sprint = Sprint.objects.for_workspace(self.workspace).get(key=kwargs["key"])

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.type_filter = self.request.GET.get("type", "").strip()
        self.assignee_filter = self.request.GET.get("assignee", "").strip()
        self.group_by = self.request.GET.get("group_by", "status").strip()
        # Sort by is only available when not grouping
        self.sort_by = self.request.GET.get("sort_by", "").strip() if not self.group_by else ""

        queryset = BaseIssue.objects.for_sprint(self.sprint).select_related(
            "project", "project__workspace", "assignee", "polymorphic_ctype"
        )

        # Apply filters
        queryset = self.apply_issue_filters(
            queryset,
            type_filter=self.type_filter,
            search_query=self.search_query,
            status_filter=self.status_filter,
            assignee_filter=self.assignee_filter,
        )

        # Apply ordering
        queryset = self.apply_issue_ordering(queryset, self.group_by, self.sort_by)

        return queryset

    def get_paginate_by(self, queryset):
        if self.group_by:
            return None  # No pagination when grouped
        return self.paginate_by

    def get_template_names(self):
        if self.request.htmx:
            target = getattr(self.request.htmx, "target", None)
            if target == "issues-list":
                return [f"{self.template_name}#list-content"]
            elif target == "issues-embed":
                return [f"{self.template_name}#embed-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sprint"] = self.sprint
        context["workspace"] = self.workspace
        context["embed_url"] = reverse(
            "sprints:sprint_issues_embed",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
                "key": self.sprint.key,
            },
        )

        # Build issue list context
        context.update(
            self.get_issue_list_context(
                search_query=self.search_query,
                status_filter=self.status_filter,
                type_filter=self.type_filter,
                assignee_filter=self.assignee_filter,
                project_filter="",
                group_by=self.group_by,
                include_group_by=True,
                extra_group_by_choices=[("project", _("Project"))],
                sort_by=self.sort_by,
            )
        )

        # Add workspace members for filter dropdowns
        context["workspace_members"] = self.request.workspace_members

        # If grouping, build grouped issues
        if self.group_by:
            issues = list(context["issues"])
            context["grouped_issues"] = build_grouped_issues(issues, self.group_by)
            # Calculate overall progress from the issues
            context["progress"] = calculate_progress(issues)

        return context


# ============================================================================
# Sprint inline editing
# ============================================================================


class SprintRowInlineEditView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Handle inline editing of sprint rows in list views."""

    def _get_context(self, request, sprint, form=None):
        """Build common context for GET/POST handlers."""
        context = {
            "sprint": sprint,
            "workspace": self.workspace,
            "workspace_members": request.workspace_members,
            "status_choices": SprintStatus.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the sprint row."""
        sprint = get_object_or_404(
            Sprint.objects.for_workspace(self.workspace).select_related("owner").with_progress(),
            key=kwargs["key"],
        )
        context = self._get_context(request, sprint)

        display_template = "sprints/includes/sprint_row.html"
        edit_template = "sprints/includes/sprint_row_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = SprintRowInlineEditForm(
            initial={
                "name": sprint.name,
                "status": sprint.status,
                "start_date": sprint.start_date,
                "end_date": sprint.end_date,
                "owner": sprint.owner,
                "capacity": sprint.capacity,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        sprint = get_object_or_404(
            Sprint.objects.for_workspace(self.workspace).select_related("owner").with_progress(),
            key=kwargs["key"],
        )
        form = SprintRowInlineEditForm(request.POST, workspace_members=request.workspace_members)
        context = self._get_context(request, sprint, form)

        display_template = "sprints/includes/sprint_row.html"
        edit_template = "sprints/includes/sprint_row_edit.html"

        if form.is_valid():
            # Update sprint fields
            sprint.name = form.cleaned_data["name"]
            sprint.status = form.cleaned_data["status"]
            # Only update dates if provided (they're required in the model but optional in inline edit)
            if form.cleaned_data.get("start_date"):
                sprint.start_date = form.cleaned_data["start_date"]
            if form.cleaned_data.get("end_date"):
                sprint.end_date = form.cleaned_data["end_date"]
            sprint.owner = form.cleaned_data.get("owner")
            sprint.capacity = form.cleaned_data.get("capacity")
            sprint.save()

            # Return display mode
            return render(request, display_template, context)

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


class SprintDetailInlineEditView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Handle inline editing of sprint details on the detail page."""

    def _get_context(self, request, sprint, form=None):
        """Build common context for GET/POST handlers."""
        # Calculate total points from work items in the sprint
        total_points = 0
        for model in [Story, Bug, Chore]:
            items = model.objects.filter(sprint=sprint)
            total_points += sum(item.estimated_points or 0 for item in items)

        context = {
            "sprint": sprint,
            "workspace": self.workspace,
            "workspace_members": request.workspace_members,
            "total_points": total_points,
            "status_choices": SprintStatus.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the sprint detail header."""
        sprint = get_object_or_404(
            Sprint.objects.for_workspace(self.workspace).select_related("owner"),
            key=kwargs["key"],
        )
        context = self._get_context(request, sprint)

        display_template = "sprints/includes/sprint_detail_header.html"
        edit_template = "sprints/includes/sprint_detail_header_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = SprintDetailInlineEditForm(
            initial={
                "name": sprint.name,
                "goal": sprint.goal,
                "status": sprint.status,
                "start_date": sprint.start_date,
                "end_date": sprint.end_date,
                "owner": sprint.owner,
                "capacity": sprint.capacity,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        sprint = get_object_or_404(
            Sprint.objects.for_workspace(self.workspace).select_related("owner"),
            key=kwargs["key"],
        )
        form = SprintDetailInlineEditForm(
            request.POST,
            workspace_members=request.workspace_members,
        )
        context = self._get_context(request, sprint, form)

        display_template = "sprints/includes/sprint_detail_header.html"
        edit_template = "sprints/includes/sprint_detail_header_edit.html"

        if form.is_valid():
            # Update sprint fields
            sprint.name = form.cleaned_data["name"]
            sprint.goal = form.cleaned_data.get("goal") or ""
            sprint.status = form.cleaned_data["status"]
            sprint.start_date = form.cleaned_data["start_date"]
            sprint.end_date = form.cleaned_data["end_date"]
            sprint.owner = form.cleaned_data.get("owner")
            sprint.capacity = form.cleaned_data.get("capacity")
            sprint.save()

            # Return display mode
            return render(request, display_template, context)

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)
