from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.issues.cascade import build_cascade_oob_response, build_cascade_retarget_response
from apps.issues.forms import (
    EpicForm,
    MilestoneDetailInlineEditForm,
    MilestoneForm,
    MilestoneRowInlineEditForm,
    get_form_class_for_type,
)
from apps.issues.helpers import (
    build_grouped_issues,
    build_htmx_delete_response,
    calculate_progress,
    count_subtasks_for_issue_ids,
    delete_subtasks_for_issue_ids,
)
from apps.issues.models import BaseIssue, IssuePriority, IssueStatus, Milestone
from apps.issues.views.mixins import ISSUE_TYPE_CHOICES
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintStatus
from apps.utils.audit import bulk_create_delete_audit_logs
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin
from apps.workspaces.models import Workspace

from .mixins import IssueListContextMixin

User = get_user_model()


class MilestoneViewMixin:
    """Base mixin for project-scoped milestone views (detail, create, update, delete).

    IMPORTANT: This mixin must override get_queryset() to use project-scoped filtering.
    """

    model = Milestone

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])
        self.project = get_object_or_404(
            Project.objects.for_workspace(self.workspace).select_related("workspace"),
            key=kwargs["project_key"],
        )

    def get_queryset(self):
        """Override TeamObjectViewMixin.get_queryset() to use project-scoped filtering."""
        return Milestone.objects.for_project(self.project)

    def get_template_names(self):
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        context["project"] = self.project
        return context


class MilestoneSingleObjectMixin:
    """Mixin for views that operate on a single milestone."""

    context_object_name = "milestone"
    slug_field = "key"
    slug_url_kwarg = "key"


class MilestoneFormMixin:
    """Mixin for views with milestone forms."""

    form_class = MilestoneForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        kwargs["workspace_members"] = self.request.workspace_members
        return kwargs


class MilestoneDetailView(
    MilestoneViewMixin,
    LoginAndWorkspaceRequiredMixin,
    MilestoneSingleObjectMixin,
    DetailView,
):
    """Display milestone details."""

    template_name = "issues/milestones/milestone_detail.html"

    def is_quick_view(self):
        return self.request.GET.get("quick_view") == "1"

    def get_template_names(self):
        if self.is_quick_view():
            return ["issues/milestones/milestone_quick_view.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_queryset(self):
        return Milestone.objects.for_project(self.project).select_related("project", "project__workspace", "owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"[{self.object.key}] {self.object.title}"
        # Calculate overall milestone progress from all descendants of linked epics
        epic_paths = list(self.object.epics.values_list("path", flat=True))
        if epic_paths:
            all_children = (
                BaseIssue.objects.filter(path__regex=r"^(" + "|".join(epic_paths) + r")")
                .filter(depth__gt=1)  # Exclude the epics themselves
                .non_polymorphic()
                .only("status", "estimated_points")
            )
        else:
            all_children = []

        context["progress"] = calculate_progress(all_children)
        return context


class MilestoneIssueListEmbedView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, IssueListContextMixin, ListView):
    """Embedded issues list for milestone detail page. Shows issues grouped by epic."""

    template_name = "issues/issues_embed.html"
    context_object_name = "issues"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.milestone = get_object_or_404(Milestone.objects.for_project(self.project), key=kwargs["key"])

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.assignee_filter = self.request.GET.get("assignee", "").strip()
        self.sprint_filter = self.request.GET.get("sprint", "").strip()
        self.priority_filter = self.request.GET.get("priority", "").strip()
        self.group_by = self.request.GET.get("group_by", "").strip()
        # Sort by is only available when not grouping; default to priority descending
        self.sort_by = self.request.GET.get("sort_by", "priority_desc").strip() if not self.group_by else ""

        # Get all issues belonging to epics linked to this milestone
        queryset = BaseIssue.objects.for_milestone(self.milestone).select_related(
            "project", "project__workspace", "assignee", "polymorphic_ctype"
        )

        # Apply filters and ordering using mixin methods (no type filter for milestone - shows epics only)
        queryset = self.apply_issue_filters(
            queryset,
            type_filter="",
            search_query=self.search_query,
            status_filter=self.status_filter,
            assignee_filter=self.assignee_filter,
            sprint_filter=self.sprint_filter,
            priority_filter=self.priority_filter,
        )
        queryset = self.apply_issue_ordering(queryset, self.group_by, self.sort_by)

        return queryset

    def get_paginate_by(self, queryset):
        if self.group_by:
            return None  # No pagination when grouped
        return self.paginate_by

    def get_template_names(self):
        if self.request.htmx:
            target = self.request.htmx.target
            if target == "issues-list":
                return [f"{self.template_name}#list-content"]
            elif target == "issues-embed":
                return [f"{self.template_name}#embed-content"]
        # Return full template for initial load or non-HTMX requests
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["milestone"] = self.milestone
        context["embed_url"] = reverse(
            "milestones:milestone_issues_embed",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
                "project_key": self.project.key,
                "key": self.milestone.key,
            },
        )
        context["workspace_members"] = self.request.workspace_members
        context.update(
            self.get_issue_list_context(
                self.search_query,
                self.status_filter,
                type_filter="",
                assignee_filter=self.assignee_filter,
                project_filter=self.project.key,
                group_by=self.group_by,
                group_by_in_modal=False,
                extra_group_by_choices=[("sprint", _("Sprint"))],
                sprint_filter=self.sprint_filter,
                include_sprint_filter=True,
                sort_by=self.sort_by,
                priority_filter=self.priority_filter,
                include_priority_filter=True,
                include_type_filter=False,
            )
        )
        context["available_sprints"] = (
            Sprint.objects.for_workspace(self.workspace)
            .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
            .order_by("-status", "-start_date")
        )
        if self.group_by:
            # Only include empty epic groups when there are no active filters
            has_active_filters = bool(
                self.search_query
                or self.status_filter
                or self.assignee_filter
                or self.sprint_filter
                or self.priority_filter
            )
            context["grouped_issues"] = build_grouped_issues(
                context["issues"],
                self.group_by,
                project=self.project,
                milestone=self.milestone,
                include_empty_epics=not has_active_filters,
            )
        if context.get("is_paginated"):
            context["elided_page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )
        return context


class MilestoneCreateView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, MilestoneFormMixin, CreateView):
    """Create a new milestone."""

    template_name = "issues/milestones/milestone_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("New Milestone")
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.project = self.project
        self.object.created_by = self.request.user
        self.object.save()

        messages.success(self.request, _("Milestone created successfully."))
        return redirect(self.object.get_absolute_url())


class MilestoneUpdateView(
    MilestoneViewMixin,
    LoginAndWorkspaceRequiredMixin,
    MilestoneSingleObjectMixin,
    MilestoneFormMixin,
    UpdateView,
):
    """Update an existing milestone."""

    template_name = "issues/milestones/milestone_form.html"

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["issues/milestones/milestone_form_modal.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_queryset(self):
        return Milestone.objects.for_project(self.project)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Edit [%(key)s] %(title)s") % {
            "key": self.object.key,
            "title": self.object.title,
        }
        return context

    def form_valid(self, form):
        # Track old status for cascade check (self.object.status is already
        # updated by ModelForm._post_clean during is_valid, so use form.initial)
        old_status = form.initial.get("status")
        self.object = form.save()
        messages.success(self.request, _("Milestone updated successfully."))
        if self.is_modal():
            new_status = self.object.status
            if old_status != new_status:
                cascade_response = build_cascade_retarget_response(self.request, self.object, new_status)
                if cascade_response:
                    return cascade_response
            project_url = reverse(
                "projects:project_detail",
                kwargs={
                    "workspace_slug": self.workspace.slug,
                    "key": self.project.key,
                },
            )
            response = HttpResponse()
            response["HX-Redirect"] = project_url
            return response
        return redirect(self.object.get_absolute_url())


class MilestoneDeleteView(
    MilestoneViewMixin,
    LoginAndWorkspaceRequiredMixin,
    MilestoneSingleObjectMixin,
    DeleteView,
):
    """Delete a milestone and cascade-delete all linked epics and their descendants."""

    template_name = "issues/milestones/milestone_confirm_delete.html"

    def get_queryset(self):
        return Milestone.objects.for_project(self.project)

    def get_template_names(self):
        if self.request.htmx:
            return ["issues/milestones/delete_confirm_content.html"]
        return [self.template_name]

    def _get_cascade_counts(self):
        """Compute epic, work item, and subtask counts for the cascade deletion."""
        epics = list(self.object.epics.all())
        epic_count = len(epics)
        all_descendant_ids = []
        for epic in epics:
            all_descendant_ids.extend(epic.get_descendants().values_list("pk", flat=True))
        work_item_count = len(all_descendant_ids)
        all_issue_ids = [e.pk for e in epics] + all_descendant_ids
        subtask_count = count_subtasks_for_issue_ids(all_issue_ids) if all_issue_ids else 0
        return epic_count, work_item_count, subtask_count, epics, all_issue_ids

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Delete [%(key)s] %(title)s") % {
            "key": self.object.key,
            "title": self.object.title,
        }
        epic_count, work_item_count, subtask_count, _epics, _ids = self._get_cascade_counts()
        context["epic_count"] = epic_count
        context["work_item_count"] = work_item_count
        context["subtask_count"] = subtask_count
        return context

    def get_success_url(self):
        return self.project.get_absolute_url()

    def form_valid(self, form):
        # Cascade: delete subtasks, audit log descendants, delete epics, then milestone
        deleted_url = self.object.get_absolute_url()
        redirect_url = self.object.project.get_absolute_url()

        epics = list(self.object.epics.all())
        all_descendants = []
        for epic in epics:
            all_descendants.extend(list(epic.get_descendants()))

        # Delete subtasks for all affected issues
        all_issue_ids = [e.pk for e in epics] + [d.pk for d in all_descendants]
        delete_subtasks_for_issue_ids(all_issue_ids)

        # Audit log descendants before bulk delete (treebeard may not fire signals)
        if all_descendants:
            bulk_create_delete_audit_logs(all_descendants, actor=self.request.user)

        # Delete each epic (treebeard handles tree descendants)
        for epic in epics:
            epic.delete()

        # Delete the milestone itself
        self.object.delete()
        messages.success(self.request, _("Milestone deleted successfully."))

        if self.request.htmx:
            return build_htmx_delete_response(self.request, deleted_url, redirect_url)

        return redirect(self.get_success_url())


class MilestoneCloneView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Clone an existing milestone."""

    def post(self, request, *args, **kwargs):
        original = get_object_or_404(Milestone.objects.for_project(self.project), key=kwargs["key"])
        cloned = Milestone.objects.create(
            project=original.project,
            title=_("%(title)s (Copy)") % {"title": original.title},
            description=original.description,
            status=original.status,
            due_date=original.due_date,
            owner=original.owner,
            priority=original.priority,
            created_by=request.user,
        )
        messages.success(request, _("Milestone cloned successfully."))
        return redirect(cloned.get_absolute_url())


class MilestoneEpicCreateView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, MilestoneSingleObjectMixin, View):
    """Create a new epic with a preset milestone and project from the milestone detail page.

    Since milestones belong to a project, the epic's project is automatically set.
    """

    template_name = "issues/milestones/epic_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.milestone = get_object_or_404(Milestone.objects.for_project(self.project), key=kwargs["key"])

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
        # Hide milestone and project fields since they're preset
        if "milestone" in form.fields:
            del form.fields["milestone"]
        if "project" in form.fields:
            del form.fields["project"]
        return form

    def get_initial(self):
        return {"milestone": self.milestone, "project": self.project}

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
            return ["issues/includes/epic_form_modal.html"]
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
        obj.milestone = self.milestone
        obj.created_by = self.request.user
        obj.key = obj._generate_unique_key()
        # Epics are root-level issues
        BaseIssue.add_root(instance=obj)

        messages.success(self.request, _("Epic created successfully."))

        # For modal submissions, close modal, reload issues list, and show toast
        if self.is_modal():
            embed_url = reverse(
                "milestones:milestone_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "project_key": self.kwargs["project_key"],
                    "key": self.milestone.key,
                },
            )
            # Render messages with out-of-band swap to show toast
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            # Return messages OOB and script to dispatch event on window for Alpine to catch
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            embed_url_with_group = embed_url + "?group_by=epic"
            script = (
                "<script>window.dispatchEvent(new CustomEvent('epic-created', "
                "{ detail: { embedUrl: '" + embed_url_with_group + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.milestone.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class MilestoneIssueCreateView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, MilestoneSingleObjectMixin, View):
    """Create a new working item (story, bug, chore, issue) with a preset milestone and optional parent epic.

    Used from the milestone detail page when clicking the + button on an epic group.
    """

    template_name = "issues/milestones/issue_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.milestone = get_object_or_404(Milestone.objects.for_project(self.project), key=kwargs["key"])
        self.issue_type = kwargs.get("issue_type", "story")
        # Get parent epic from query parameter
        parent_key = request.GET.get("parent")
        self.parent = None
        if parent_key:
            self.parent = BaseIssue.objects.for_project(self.project).filter(key=parent_key).first()

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
        # Hide parent and project fields since they're preset
        if "parent" in form.fields:
            del form.fields["parent"]
        if "project" in form.fields:
            del form.fields["project"]
        return form

    def get_initial(self):
        return {"project": self.project, "parent": self.parent}

    def get_context_data(self, **kwargs):
        context = {
            "workspace": self.workspace,
            "project": self.project,
            "milestone": self.milestone,
            "parent": self.parent,
            "form": kwargs.get("form", self.get_form()),
            "issue_type": self.issue_type,
            "issue_type_label": dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue")),
        }
        return context

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["issues/includes/issue_create_form_modal.html"]
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
        obj.key = obj._generate_unique_key()

        if self.parent:
            self.parent.add_child(instance=obj)
        else:
            BaseIssue.add_root(instance=obj)

        issue_type_label = dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue"))
        messages.success(
            self.request,
            _("%(type)s created successfully.") % {"type": issue_type_label},
        )

        # For modal submissions, close modal, reload issues list, and show toast
        if self.is_modal():
            embed_url = reverse(
                "milestones:milestone_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "project_key": self.kwargs["project_key"],
                    "key": self.milestone.key,
                },
            )
            # Render messages with out-of-band swap to show toast
            messages_html = render_to_string(
                "includes/messages.html",
                {"messages": messages.get_messages(self.request)},
                request=self.request,
            )
            # Return messages OOB and script to dispatch event on window for Alpine to catch
            messages_div = (
                f'<div id="messages" class="toast toast-end toast-bottom z-50" hx-swap-oob="true">{messages_html}</div>'
            )
            embed_url_with_group = embed_url + "?group_by=epic"
            script = (
                "<script>window.dispatchEvent(new CustomEvent('issue-created', "
                "{ detail: { embedUrl: '" + embed_url_with_group + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.milestone.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


# ============================================================================
# Milestone inline editing
# ============================================================================


class MilestoneRowInlineEditView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Handle inline editing of milestone rows in list views."""

    def _get_context(self, request, milestone, form=None):
        """Build common context for GET/POST handlers."""
        context = {
            "milestone": milestone,
            "workspace": self.workspace,
            "project": self.project,
            "workspace_members": request.workspace_members,
            "status_choices": IssueStatus.choices,
            "priority_choices": IssuePriority.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the milestone row."""
        milestone = get_object_or_404(
            Milestone.objects.for_project(self.project).select_related("owner"),
            key=kwargs["key"],
        )
        context = self._get_context(request, milestone)

        display_template = "issues/includes/milestone_row.html"
        edit_template = "issues/includes/milestone_row_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = MilestoneRowInlineEditForm(
            initial={
                "title": milestone.title,
                "status": milestone.status,
                "priority": milestone.priority,
                "owner": milestone.owner,
                "due_date": milestone.due_date,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        milestone = get_object_or_404(
            Milestone.objects.for_project(self.project).select_related("owner"),
            key=kwargs["key"],
        )
        form = MilestoneRowInlineEditForm(request.POST, workspace_members=request.workspace_members)
        context = self._get_context(request, milestone, form)

        display_template = "issues/includes/milestone_row.html"
        edit_template = "issues/includes/milestone_row_edit.html"

        if form.is_valid():
            old_status = milestone.status

            # Update milestone fields
            milestone.title = form.cleaned_data["title"]
            milestone.status = form.cleaned_data["status"]
            milestone.priority = form.cleaned_data.get("priority") or ""
            milestone.owner = form.cleaned_data.get("owner")
            milestone.due_date = form.cleaned_data.get("due_date")
            milestone.save()

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, milestone, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


class MilestoneDetailInlineEditView(MilestoneViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Handle inline editing of milestone details on the detail page."""

    def _get_context(self, request, milestone, form=None):
        """Build common context for GET/POST handlers."""
        context = {
            "milestone": milestone,
            "workspace": self.workspace,
            "project": self.project,
            "workspace_members": request.workspace_members,
            "status_choices": IssueStatus.choices,
            "priority_choices": IssuePriority.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the milestone detail header."""
        milestone = get_object_or_404(
            Milestone.objects.for_project(self.project).select_related("owner"),
            key=kwargs["key"],
        )
        context = self._get_context(request, milestone)

        display_template = "issues/includes/milestone_detail_header.html"
        edit_template = "issues/includes/milestone_detail_header_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = MilestoneDetailInlineEditForm(
            initial={
                "title": milestone.title,
                "description": milestone.description,
                "status": milestone.status,
                "priority": milestone.priority,
                "owner": milestone.owner,
                "due_date": milestone.due_date,
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        milestone = get_object_or_404(
            Milestone.objects.for_project(self.project).select_related("owner"),
            key=kwargs["key"],
        )
        form = MilestoneDetailInlineEditForm(request.POST, workspace_members=request.workspace_members)
        context = self._get_context(request, milestone, form)

        display_template = "issues/includes/milestone_detail_header.html"
        edit_template = "issues/includes/milestone_detail_header_edit.html"

        if form.is_valid():
            old_status = milestone.status

            # Update milestone fields
            milestone.title = form.cleaned_data["title"]
            milestone.description = form.cleaned_data.get("description") or ""
            milestone.status = form.cleaned_data["status"]
            milestone.priority = form.cleaned_data.get("priority") or ""
            milestone.owner = form.cleaned_data.get("owner")
            milestone.due_date = form.cleaned_data.get("due_date")
            milestone.save()

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, milestone, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


# Backwards compatibility alias
WorkspaceEpicCreateView = MilestoneEpicCreateView
