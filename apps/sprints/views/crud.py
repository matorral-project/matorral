from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.issues.helpers import build_grouped_issues, build_htmx_delete_response
from apps.issues.models import BaseIssue
from apps.issues.views.mixins import WORK_ITEM_TYPE_CHOICES, IssueListContextMixin
from apps.sprints.forms import SprintDetailInlineEditForm, SprintForm, SprintRowInlineEditForm
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.views.mixins import SprintFormMixin, SprintListContextMixin, SprintSingleObjectMixin, SprintViewMixin
from apps.utils.progress import calculate_progress
from apps.workspaces.helpers import clear_onboarding_session_cache
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
            sprint.progress = sprint.get_progress()

        return context


class SprintDetailView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, DetailView):
    """Display sprint details."""

    template_name = "sprints/sprint_detail.html"

    def get_queryset(self):
        return (
            Sprint.objects.for_workspace(self.workspace)
            .select_related("workspace", "owner")
            .with_progress()
            .with_velocity()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sprint = self.object
        context["page_title"] = sprint.name

        # For active sprints, use real-time completed_points from annotation
        if sprint.status == SprintStatus.ACTIVE:
            sprint.completed_points = sprint.computed_completed_points

        context["progress"] = sprint.get_progress()

        # Count items and total points from annotations
        context["item_count"] = BaseIssue.objects.for_sprint(sprint).count()
        context["total_points"] = sprint.computed_committed_points

        return context


class SprintCreateView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintFormMixin, CreateView):
    """Create a new sprint."""

    template_name = "sprints/sprint_form.html"
    form_class = SprintForm

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["sprints/includes/sprint_form_modal.html"]
        if self.request.htmx and not self.request.htmx.history_restore_request:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("New Sprint")
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.workspace = self.workspace
        self.object.created_by = self.request.user
        self.object.save()
        clear_onboarding_session_cache(self.request)
        messages.success(self.request, _("Sprint created successfully."))

        if self.is_modal():
            list_url = reverse("sprints:sprint_list", kwargs={"workspace_slug": self.workspace.slug})
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('sprint-created', "
                "{ detail: { listUrl: '" + list_url + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.object.get_absolute_url())

    def get_initial(self):
        return Sprint.objects.get_creation_defaults(self.workspace, self.request.workspace_members)


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

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["sprints/includes/sprint_form_modal.html"]
        if self.request.htmx and not self.request.htmx.history_restore_request:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_queryset(self):
        return Sprint.objects.for_workspace(self.workspace)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Edit %s") % self.object.name
        return context

    def form_valid(self, form):
        self.object = form.save()
        messages.success(self.request, _("Sprint updated successfully."))

        if self.is_modal():
            list_url = reverse("sprints:sprint_list", kwargs={"workspace_slug": self.workspace.slug})
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            script = (
                "<script>window.dispatchEvent(new CustomEvent('sprint-updated', "
                "{ detail: { listUrl: '" + list_url + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

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
        context["item_count"] = BaseIssue.objects.for_sprint(self.object).count()
        return context

    def get_success_url(self):
        return reverse(
            "sprints:sprint_list",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
            },
        )

    def form_valid(self, form):
        deleted_url = self.object.get_absolute_url()
        redirect_url = self.get_success_url()

        self.object.delete()
        messages.success(self.request, _("Sprint deleted successfully."))

        if self.request.htmx:
            return build_htmx_delete_response(self.request, deleted_url, redirect_url)

        return redirect(redirect_url)


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

        queryset = (
            BaseIssue.objects.work_items()
            .for_sprint(self.sprint)
            .select_related("project", "project__workspace", "assignee", "polymorphic_ctype")
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
                group_by_in_modal=False,
                extra_group_by_choices=[("project", _("Project"))],
                sort_by=self.sort_by,
                type_filter_type="multi_select",
                type_filter_choices=WORK_ITEM_TYPE_CHOICES,
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

    def _get_sprint_queryset(self):
        return Sprint.objects.for_workspace(self.workspace).select_related("owner").with_committed_points()

    def _get_context(self, request, sprint, form=None):
        """Build common context for GET/POST handlers."""
        context = {
            "sprint": sprint,
            "workspace": self.workspace,
            "workspace_members": request.workspace_members,
            "total_points": sprint.computed_committed_points,
            "status_choices": SprintStatus.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the sprint detail header."""
        sprint = get_object_or_404(
            self._get_sprint_queryset(),
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
            self._get_sprint_queryset(),
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
