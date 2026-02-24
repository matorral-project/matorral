from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from apps.issues.cascade import build_cascade_oob_response, build_cascade_retarget_response
from apps.issues.forms import (
    ISSUE_TYPES,
    EpicDetailInlineEditForm,
    IssueConvertTypeForm,
    IssueDetailInlineEditForm,
    IssuePromoteToEpicForm,
    IssueRowInlineEditForm,
    get_form_class_for_type,
)
from apps.issues.helpers import (
    annotate_epic_child_counts,
    build_grouped_issues,
    build_htmx_delete_response,
    count_subtasks_for_issue_ids,
    delete_subtasks_for_issue_ids,
)
from apps.issues.models import BaseIssue, Bug, BugSeverity, Epic, IssuePriority, IssueStatus, Milestone
from apps.issues.utils import get_cached_content_type
from apps.projects.models import Project
from apps.sprints.models import Sprint, SprintStatus
from apps.workspaces.limits import LimitExceededError, check_work_item_limit
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from .mixins import (
    ISSUE_TYPE_CHOICES,
    WORK_ITEM_TYPE_CHOICES,
    IssueFormMixin,
    IssueListContextMixin,
    IssueSingleObjectMixin,
    IssueViewMixin,
    WorkspaceIssueViewMixin,
)


class WorkspaceIssueListView(
    LoginAndWorkspaceRequiredMixin,
    IssueListContextMixin,
    WorkspaceIssueViewMixin,
    ListView,
):
    """List all issues across all projects in a workspace with filtering and pagination."""

    template_name = "issues/workspace_issue_list.html"
    context_object_name = "issues"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def get_queryset(self):
        self.search_query = self.request.GET.get("search", "").strip()
        self.status_filter = self.request.GET.get("status", "").strip()
        self.type_filter = self.request.GET.get("type", "").strip()
        self.assignee_filter = self.request.GET.get("assignee", "").strip()
        self.project_filter = self.request.GET.get("project", "").strip()
        self.sprint_filter = self.request.GET.get("sprint", "").strip()
        # Group by is only available when filtering by project
        self.group_by = self.request.GET.get("group_by", "").strip() if self.project_filter else ""
        # Sort by is only available when not grouping
        self.sort_by = self.request.GET.get("sort_by", "").strip() if not self.group_by else ""

        # Validate project filter if provided
        self.filtered_project = None
        if self.project_filter:
            self.filtered_project = get_object_or_404(
                Project.objects.for_workspace(self.workspace), key=self.project_filter
            )

        # Get all issues in workspace (or filtered project)
        if self.filtered_project:
            queryset = BaseIssue.objects.for_project(self.filtered_project).select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )
        else:
            queryset = BaseIssue.objects.for_workspace(self.workspace).select_related(
                "project", "project__workspace", "assignee", "polymorphic_ctype"
            )

        # Apply filters and ordering using mixin methods
        queryset = self.apply_issue_filters(
            queryset,
            self.type_filter,
            self.search_query,
            self.status_filter,
            self.assignee_filter,
            self.sprint_filter,
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
            if target == "list-content":
                return [f"{self.template_name}#list-content"]
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Issues")
        context["workspace_members"] = self.request.workspace_members
        context.update(
            self.get_issue_list_context(
                self.search_query,
                self.status_filter,
                self.type_filter,
                self.assignee_filter,
                self.project_filter,
                self.group_by,
                sprint_filter=self.sprint_filter,
                include_sprint_filter=True,
                sort_by=self.sort_by,
            )
        )
        if self.group_by:
            context["grouped_issues"] = build_grouped_issues(
                context["issues"], self.group_by, project=self.filtered_project
            )
        if context.get("is_paginated"):
            context["elided_page_range"] = context["paginator"].get_elided_page_range(
                context["page_obj"].number, on_each_side=2, on_ends=1
            )
        return context


class WorkspaceIssueCreateView(LoginAndWorkspaceRequiredMixin, WorkspaceIssueViewMixin, View):
    """Create a new issue at workspace level with project selector.

    Used from the workspace issues list when clicking the + New dropdown.
    Supports modal mode for inline creation.
    """

    template_name = "issues/issue_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.issue_type = kwargs.get("issue_type", "story")

    def get_form_class(self):
        return get_form_class_for_type(self.issue_type)

    def get_form_kwargs(self):
        kwargs = {
            "project": None,  # Project will be selected in the form
            "workspace_members": self.request.workspace_members,
        }
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return kwargs

    def get_form(self):
        form = self.get_form_class()(**self.get_form_kwargs())
        # Set up project queryset to show all projects in workspace
        if "project" in form.fields:
            form.fields["project"].queryset = Project.objects.for_workspace(self.workspace).for_choices()
        return form

    def get_context_data(self, **kwargs):
        context = {
            "workspace": self.workspace,
            "form": kwargs.get("form", self.get_form()),
            "issue_type": self.issue_type,
            "issue_type_label": dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue")),
        }
        return context

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["issues/includes/workspace_issue_create_form_modal.html"]
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
        try:
            check_work_item_limit(self.workspace)
        except LimitExceededError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        obj = form.save(commit=False)
        obj.created_by = self.request.user
        obj.key = obj._generate_unique_key()

        # Get parent from form if provided
        parent = form.cleaned_data.get("parent")

        if parent:
            parent.add_child(instance=obj)
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
                "workspace_issue_list",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
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
            script = (
                "<script>window.dispatchEvent(new CustomEvent('issue-created', "
                "{ detail: { embedUrl: '" + embed_url + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        # For non-modal submissions, redirect to the issue detail page
        return redirect(obj.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class IssueDetailView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, IssueSingleObjectMixin, DetailView):
    """Display issue details."""

    template_name = "issues/issue_detail.html"

    def is_quick_view(self):
        return self.request.GET.get("quick_view") == "1"

    def get_template_names(self):
        if self.is_quick_view():
            return ["issues/includes/issue_quick_view.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_queryset(self):
        return BaseIssue.objects.for_project(self.project).select_related(
            "project", "project__workspace", "assignee", "polymorphic_ctype"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        issue = context["issue"]
        context["page_title"] = f"[{issue.key}] {issue.title}"
        context["children"] = issue.get_children_issues()
        context["parent"] = issue.get_parent_issue()

        # Set appropriate label for children based on issue type
        issue_type = issue.get_issue_type()
        if issue_type == "epic":
            context["children_label"] = _("Issues")
            # Show linked milestone if any
            context["milestone"] = issue.milestone
            # Calculate progress from children
            context["progress"] = issue.get_progress()
        else:
            context["children_label"] = _("Children")
            # Needed for inline editing to show severity field for bugs
            context["is_bug"] = isinstance(issue, Bug)

        return context


class IssueCreateView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, IssueFormMixin, CreateView):
    """Create a new issue."""

    template_name = "issues/issue_form.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # Check if parent is preset from query parameter (self.project is set by IssueViewMixin.setup)
        self.parent_preset = None
        parent_key = request.GET.get("parent")
        if parent_key:
            self.parent_preset = BaseIssue.objects.for_project(self.project).filter(key=parent_key).first()
        # Check if project should be locked (not editable) - used when creating from project detail page
        # Supports both ?project_locked=true and ?project=<KEY> patterns
        self.project_locked = request.GET.get("project_locked") == "true" or request.GET.get("project")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["issue_type"] = self.kwargs.get("issue_type", "story")
        context["issue_type_label"] = dict(ISSUE_TYPE_CHOICES).get(context["issue_type"], _("Story"))
        context["page_title"] = _("New %s") % context["issue_type_label"]
        context["issue_types"] = ISSUE_TYPES
        context["parent_preset"] = self.parent_preset
        context["project_locked"] = self.project_locked
        context["next_url"] = self.request.GET.get("next")
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Hide parent and project fields when parent is preset
        if self.parent_preset:
            if "parent" in form.fields:
                del form.fields["parent"]
            if "project" in form.fields:
                del form.fields["project"]
        # Hide project field when locked (creating from project detail page)
        elif self.project_locked:
            if "project" in form.fields:
                del form.fields["project"]
        return form

    def get_initial(self):
        initial = super().get_initial()
        initial["project"] = self.project
        # Pre-set parent from query parameter if provided
        if self.parent_preset:
            initial["parent"] = self.parent_preset
        return initial

    def form_valid(self, form):
        try:
            check_work_item_limit(self.workspace)
        except LimitExceededError as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        # Use preset parent if available, otherwise get from form
        parent = self.parent_preset or form.cleaned_data.get("parent")

        obj = form.save(commit=False)
        # Set project if project field was removed from form
        if not obj.project_id:
            if self.parent_preset:
                obj.project = self.parent_preset.project
            elif self.project_locked:
                obj.project = self.project
        obj.created_by = self.request.user
        obj.key = obj.key or obj._generate_unique_key()

        if parent:
            # Add as child of parent
            saved_obj = parent.add_child(instance=obj)
            self.object = saved_obj
        else:
            # Add as root
            saved_obj = BaseIssue.add_root(instance=obj)
            self.object = saved_obj

        messages.success(
            self.request,
            _("%(type)s created successfully.") % {"type": self.object.get_issue_type_display()},
        )
        # Redirect to 'next' URL if provided, otherwise to the new issue's detail page
        next_url = self.request.GET.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(self.object.get_absolute_url())


class IssueUpdateView(
    LoginAndWorkspaceRequiredMixin,
    IssueViewMixin,
    IssueSingleObjectMixin,
    IssueFormMixin,
    UpdateView,
):
    """Update an existing issue."""

    template_name = "issues/issue_form.html"

    def get_template_names(self):
        if self.request.GET.get("modal") == "1":
            return ["issues/includes/issue_form_modal.html"]
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_queryset(self):
        return BaseIssue.objects.for_project(self.project)

    def get_initial(self):
        initial = super().get_initial()
        # Set initial parent value
        parent = self.object.get_parent_issue()
        if parent:
            initial["parent"] = parent
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["issue_type"] = self.object.get_issue_type()
        context["issue_type_label"] = self.object.get_issue_type_display()
        context["page_title"] = _("Edit [%(key)s] %(title)s") % {
            "key": self.object.key,
            "title": self.object.title,
        }
        return context

    def form_valid(self, form):
        # Track old status for cascade check (self.object.status is already
        # updated by ModelForm._post_clean during is_valid, so use form.initial)
        old_status = form.initial.get("status")

        # Handle parent change (move in tree)
        new_parent = form.cleaned_data.get("parent")
        current_parent = self.object.get_parent_issue()

        # Save the form (updates fields)
        self.object = form.save()

        # Handle tree restructuring if parent changed
        if new_parent != current_parent:
            if new_parent is None:
                # Move to root - use 'last-sibling' to append without path shuffling
                any_root = BaseIssue.get_first_root_node()
                if any_root:
                    self.object.move(any_root, pos="last-sibling")
            else:
                # Move under new parent
                self.object.move(new_parent, pos="last-child")

        messages.success(
            self.request,
            _("%(type)s updated successfully.") % {"type": self.object.get_issue_type_display()},
        )

        # For modal submissions, check cascade opportunities if status changed
        if self.request.GET.get("modal") == "1":
            new_status = self.object.status
            if old_status != new_status:
                cascade_response = build_cascade_retarget_response(self.request, self.object, new_status)
                if cascade_response:
                    return cascade_response
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return redirect(self.object.get_absolute_url())


class IssueDeleteView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, IssueSingleObjectMixin, DeleteView):
    """Delete an issue."""

    template_name = "issues/issue_confirm_delete.html"

    def get_queryset(self):
        return BaseIssue.objects.for_project(self.project)

    def get_template_names(self):
        if self.request.htmx:
            return ["issues/includes/delete_confirm_content.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Delete [%(key)s] %(title)s") % {
            "key": self.object.key,
            "title": self.object.title,
        }
        context["descendant_count"] = self.object.get_descendant_count()
        # Collect all issue IDs (self + descendants) for subtask count
        descendant_ids = list(self.object.get_descendants().values_list("pk", flat=True))
        all_ids = [self.object.pk] + descendant_ids
        context["subtask_count"] = count_subtasks_for_issue_ids(all_ids)
        return context

    def get_success_url(self):
        base_url = reverse(
            "workspace_issue_list",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
            },
        )
        return f"{base_url}?project={self.kwargs['project_key']}"

    def _get_htmx_redirect_url(self):
        """Return the URL to redirect to after HTMX deletion.

        Redirect targets by issue type:
        - Epic (root issue) → parent project's detail page
        - Story/Bug (child of epic) → parent epic's detail page
        """
        parent = self.object.get_parent_issue()
        if parent:
            return parent.get_absolute_url()
        return self.object.project.get_absolute_url()

    def form_valid(self, form):
        issue_type = self.object.get_issue_type_display()
        deleted_url = self.object.get_absolute_url()
        redirect_url = self._get_htmx_redirect_url()

        # Delete subtasks before issue deletion (GenericFK won't cascade)
        descendant_ids = list(self.object.get_descendants().values_list("pk", flat=True))
        all_ids = [self.object.pk] + descendant_ids
        delete_subtasks_for_issue_ids(all_ids)
        self.object.delete()
        messages.success(self.request, _("%(type)s deleted successfully.") % {"type": issue_type})

        if self.request.htmx:
            return build_htmx_delete_response(self.request, deleted_url, redirect_url)

        return redirect(self.get_success_url())


class IssueCloneView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Clone an existing issue."""

    def post(self, request, *args, **kwargs):
        try:
            check_work_item_limit(self.workspace)
        except LimitExceededError as e:
            messages.error(request, str(e))
            return redirect(
                reverse(
                    "issues:issue_detail",
                    kwargs={
                        "workspace_slug": kwargs["workspace_slug"],
                        "project_key": kwargs["project_key"],
                        "key": kwargs["key"],
                    },
                )
            )

        original = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        parent = original.get_parent_issue()

        # Create clone with copy suffix
        clone_data = {
            "project": original.project,
            "title": _("%(title)s (Copy)") % {"title": original.title},
            "description": original.description,
            "status": original.status,
            "due_date": original.due_date,
            "created_by": request.user,
        }

        # Handle type-specific fields
        if hasattr(original, "owner"):
            clone_data["owner"] = original.owner
        if hasattr(original, "priority"):
            clone_data["priority"] = original.priority
        if hasattr(original, "assignee"):
            clone_data["assignee"] = original.assignee
        if hasattr(original, "estimated_points"):
            clone_data["estimated_points"] = original.estimated_points
        if hasattr(original, "severity"):
            clone_data["severity"] = original.severity

        # Create the clone using the same model class
        model_class = type(original)
        cloned = model_class(**clone_data)
        cloned.key = cloned._generate_unique_key()

        saved_clone = parent.add_child(instance=cloned) if parent else BaseIssue.add_root(instance=cloned)

        messages.success(
            request,
            _("%(type)s cloned successfully.") % {"type": saved_clone.get_issue_type_display()},
        )

        # For HTMX requests, return HX-Refresh to reload the page
        if request.htmx:
            response = HttpResponse()
            response["HX-Refresh"] = "true"
            return response

        return redirect(saved_clone.get_absolute_url())


class IssueConvertTypeView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Convert an issue to a different type (Story, Bug, Chore, Issue)."""

    def get(self, request, *args, **kwargs):
        """Return the modal content with type selection."""
        from django.shortcuts import render

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        real_issue = issue.get_real_instance()
        current_type = real_issue.get_issue_type()

        # Epics cannot be converted
        if current_type == "epic":
            messages.error(request, _("Epics cannot be converted to another type."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(real_issue.get_absolute_url())

        form = IssueConvertTypeForm(current_type=current_type)

        source = request.GET.get("source", "")
        context = {
            "issue": real_issue,
            "form": form,
            "current_type": current_type,
            "workspace": self.workspace,
            "project": self.project,
            "source": source,
        }
        return render(request, "issues/includes/issue_convert_modal_content.html", context)

    def post(self, request, *args, **kwargs):
        """Perform the type conversion."""

        from django.shortcuts import render

        from apps.issues.services import IssueConversionError, convert_issue_type

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        real_issue = issue.get_real_instance()
        current_type = real_issue.get_issue_type()

        # Epics cannot be converted
        if current_type == "epic":
            messages.error(request, _("Epics cannot be converted to another type."))
            if request.htmx:
                response = render(request, "includes/messages.html")
                return response
            return redirect(real_issue.get_absolute_url())

        source = request.POST.get("source", "")
        form = IssueConvertTypeForm(request.POST, current_type=current_type)

        if form.is_valid():
            target_type = form.cleaned_data["target_type"]
            severity = form.cleaned_data.get("severity")

            try:
                converted = convert_issue_type(real_issue, target_type, severity=severity)
                messages.success(
                    request,
                    _("%(key)s converted from %(old)s to %(new)s.")
                    % {
                        "key": converted.key,
                        "old": current_type.title(),
                        "new": target_type.title(),
                    },
                )

                if request.htmx:
                    response = HttpResponse()
                    if source in ("list", "embed"):
                        response["HX-Trigger"] = "issueChanged"
                    else:
                        response["HX-Redirect"] = converted.get_absolute_url()
                    return response

                return redirect(converted.get_absolute_url())

            except IssueConversionError as e:
                messages.error(request, str(e))
                if request.htmx:
                    return render(request, "includes/messages.html")
                return redirect(real_issue.get_absolute_url())

        # Form validation failed
        context = {
            "issue": real_issue,
            "form": form,
            "current_type": current_type,
            "workspace": self.workspace,
            "project": self.project,
            "source": source,
        }
        return render(request, "issues/includes/issue_convert_modal_content.html", context)


class IssuePromoteToEpicView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Promote a work item (Story, Bug, Chore, Issue) to an Epic."""

    def get(self, request, *args, **kwargs):
        """Return the modal content with promotion options."""
        from django.shortcuts import render

        from apps.issues.models import Subtask

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        real_issue = issue.get_real_instance()
        current_type = real_issue.get_issue_type()

        # Epics cannot be promoted
        if current_type == "epic":
            messages.error(request, _("Epic cannot be promoted to Epic."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(real_issue.get_absolute_url())

        # Preselect parent epic's milestone if available
        initial = {}
        parent = real_issue.get_parent()
        if parent:
            parent_real = parent.get_real_instance()
            if isinstance(parent_real, Epic) and parent_real.milestone_id:
                initial["milestone"] = parent_real.milestone_id

        form = IssuePromoteToEpicForm(initial=initial, project=self.project)

        # Get subtask count for display
        content_type = get_cached_content_type(type(real_issue))
        subtask_count = Subtask.objects.filter(content_type=content_type, object_id=real_issue.pk).count()

        source = request.GET.get("source", "")
        context = {
            "issue": real_issue,
            "form": form,
            "current_type": current_type,
            "workspace": self.workspace,
            "project": self.project,
            "subtask_count": subtask_count,
            "has_sprint": hasattr(real_issue, "sprint") and real_issue.sprint is not None,
            "has_points": hasattr(real_issue, "estimated_points") and real_issue.estimated_points is not None,
            "is_bug": current_type == "bug",
            "source": source,
        }
        return render(request, "issues/includes/issue_promote_modal_content.html", context)

    def post(self, request, *args, **kwargs):
        """Perform the promotion to Epic."""

        from django.shortcuts import render

        from apps.issues.services import PromotionError, promote_to_epic

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        real_issue = issue.get_real_instance()
        current_type = real_issue.get_issue_type()

        # Epics cannot be promoted
        if current_type == "epic":
            messages.error(request, _("Epic cannot be promoted to Epic."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(real_issue.get_absolute_url())

        source = request.POST.get("source", "")
        form = IssuePromoteToEpicForm(request.POST, project=self.project)

        if form.is_valid():
            milestone = form.cleaned_data.get("milestone")
            convert_subtasks = form.cleaned_data.get("convert_subtasks", True)

            try:
                epic = promote_to_epic(real_issue, milestone=milestone, convert_subtasks=convert_subtasks)
                messages.success(
                    request,
                    _("%(key)s promoted from %(old)s to Epic.")
                    % {
                        "key": epic.key,
                        "old": current_type.title(),
                    },
                )

                if request.htmx:
                    response = HttpResponse()
                    if source in ("list", "embed"):
                        response["HX-Trigger"] = "issueChanged"
                    else:
                        response["HX-Redirect"] = epic.get_absolute_url()
                    return response

                return redirect(epic.get_absolute_url())

            except PromotionError as e:
                messages.error(request, str(e))
                if request.htmx:
                    return render(request, "includes/messages.html")
                return redirect(real_issue.get_absolute_url())

        # Form validation failed - re-render modal content
        from apps.issues.models import Subtask

        content_type = get_cached_content_type(type(real_issue))
        subtask_count = Subtask.objects.filter(content_type=content_type, object_id=real_issue.pk).count()

        context = {
            "issue": real_issue,
            "form": form,
            "current_type": current_type,
            "workspace": self.workspace,
            "project": self.project,
            "subtask_count": subtask_count,
            "has_sprint": hasattr(real_issue, "sprint") and real_issue.sprint is not None,
            "has_points": hasattr(real_issue, "estimated_points") and real_issue.estimated_points is not None,
            "is_bug": current_type == "bug",
            "source": source,
        }
        return render(request, "issues/includes/issue_promote_modal_content.html", context)


class EpicIssueListEmbedView(LoginAndWorkspaceRequiredMixin, IssueListContextMixin, IssueViewMixin, ListView):
    """Embedded issues list for epic detail page. Shows children of an epic with filtering."""

    template_name = "issues/issues_embed.html"
    context_object_name = "issues"
    paginate_by = settings.DEFAULT_PAGE_SIZE

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.epic = get_object_or_404(
            Epic.objects.for_project(self.project).select_related("project", "project__workspace"),
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
        # Sort by is only available when not grouping
        self.sort_by = self.request.GET.get("sort_by", "").strip() if not self.group_by else ""

        # Get all children of the epic
        # Note: sprint is on concrete work item models, not BaseIssue, so can't select_related it here
        queryset = self.epic.get_children().select_related(
            "project", "project__workspace", "assignee", "polymorphic_ctype"
        )

        # Apply filters and ordering using mixin methods
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
        context["epic"] = self.epic
        context["embed_url"] = reverse(
            "issues:epic_issues_embed",
            kwargs={
                "workspace_slug": self.kwargs["workspace_slug"],
                "project_key": self.project.key,
                "key": self.epic.key,
            },
        )
        context["workspace_members"] = self.request.workspace_members

        # Build group-by choices: exclude "epic" (we're in an epic), add "sprint"
        epic_group_by_choices = [
            ("sprint", _("Sprint")),
            ("status", _("Status")),
            ("priority", _("Priority")),
            ("assignee", _("Assignee")),
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
                extra_group_by_choices=epic_group_by_choices,
                exclude_epic_group_by=True,
                sort_by=self.sort_by,
                priority_filter=self.priority_filter,
                include_priority_filter=True,
                type_filter_type="multi_select",
                type_filter_choices=WORK_ITEM_TYPE_CHOICES,
            )
        )
        # Get available sprints for bulk add-to-sprint action
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


class EpicIssueCreateView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Create a new work item (story, bug, chore, issue) as a child of an epic, via modal."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.epic = get_object_or_404(Epic.objects.for_project(self.project), key=kwargs["key"])
        self.issue_type = kwargs.get("issue_type", "story")

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
        if "parent" in form.fields:
            del form.fields["parent"]
        if "project" in form.fields:
            del form.fields["project"]
        return form

    def get_context_data(self, **kwargs):
        return {
            "workspace": self.workspace,
            "project": self.project,
            "parent": self.epic,
            "form": kwargs.get("form", self.get_form()),
            "issue_type": self.issue_type,
            "issue_type_label": dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue")),
        }

    def is_modal(self):
        return self.request.GET.get("modal") == "1"

    def get_template_names(self):
        if self.is_modal():
            return ["issues/includes/issue_create_form_modal.html"]
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
        obj = form.save(commit=False)
        obj.project = self.project
        obj.created_by = self.request.user
        obj.key = obj._generate_unique_key()

        self.epic.add_child(instance=obj)

        issue_type_label = dict(ISSUE_TYPE_CHOICES).get(self.issue_type, _("Issue"))
        messages.success(
            self.request,
            _("%(type)s created successfully.") % {"type": issue_type_label},
        )

        if self.is_modal():
            embed_url = reverse(
                "issues:epic_issues_embed",
                kwargs={
                    "workspace_slug": self.kwargs["workspace_slug"],
                    "project_key": self.kwargs["project_key"],
                    "key": self.epic.key,
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
                "{ detail: { embedUrl: '" + embed_url + "' } }));</script>"
            )
            return HttpResponse(messages_div + script)

        return redirect(self.epic.get_absolute_url())

    def form_invalid(self, form):
        context = self.get_context_data(form=form)
        return render(self.request, self.get_template_names()[0], context)


class IssueRowInlineEditView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Handle inline editing of issue rows in list views."""

    def _get_context(self, request, issue, form=None):
        """Build common context for GET/POST handlers."""
        real_issue = issue.get_real_instance()
        is_epic = isinstance(real_issue, Epic)

        # Determine which columns to show (default to all for standalone usage)
        show_status = request.GET.get("show_status", "1") != "0"
        show_priority = request.GET.get("show_priority", "1") != "0"
        show_assignee = request.GET.get("show_assignee", "1") != "0"

        # Check if this is for an embedded list or dashboard
        embed_value = request.GET.get("embed", "") or request.POST.get("embed", "")
        is_embed = embed_value == "1"
        is_project_epics_embed = embed_value == "project_epics"
        is_project_epic_children_embed = embed_value == "project_epic_children"
        is_project_orphan_embed = embed_value == "project_orphan"
        is_dashboard = request.GET.get("dashboard") == "1" or request.POST.get("dashboard") == "1"

        # Check if sprint context
        sprint = None
        sprint_key = request.GET.get("sprint")
        if sprint_key:
            sprint = Sprint.objects.for_workspace(self.workspace).filter(key=sprint_key).first()

        # Derive group_by from show_* params (for issue_row.html template)
        group_by = ""
        if not show_status:
            group_by = "status"
        elif not show_priority:
            group_by = "priority"
        elif not show_assignee:
            group_by = "assignee"

        context = {
            "issue": real_issue,
            "workspace": self.workspace,
            "project": self.project,
            "workspace_members": request.workspace_members,
            "is_epic": is_epic,
            "has_priority": hasattr(real_issue, "priority"),
            "show_status": show_status,
            "show_priority": show_priority,
            "show_assignee": show_assignee,
            "show_project": sprint is not None and group_by != "project",
            "group_by": group_by,
            "status_choices": IssueStatus.choices,
            "priority_choices": IssuePriority.choices,
            "is_embed": is_embed,
            "is_project_epics_embed": is_project_epics_embed,
            "is_project_epic_children_embed": is_project_epic_children_embed,
            "is_project_orphan_embed": is_project_orphan_embed,
            "is_dashboard": is_dashboard,
            "sprint": sprint,
        }
        if is_project_epics_embed:
            annotate_epic_child_counts([real_issue])
            context["epic"] = real_issue
            context["inline_edit"] = True
        if is_project_epic_children_embed:
            context["child"] = real_issue
            context["parent_key"] = request.GET.get("parent_key", "") or request.POST.get("parent_key", "")
        if is_project_orphan_embed:
            context["item"] = real_issue
        if form:
            context["form"] = form
        return context, real_issue

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the issue row."""
        from django.shortcuts import render

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        context, real_issue = self._get_context(request, issue)

        # Determine template based on context (embed, dashboard, or default)
        if context["is_project_orphan_embed"]:
            display_template = "projects/includes/orphan_work_item_row.html"
            edit_template = "projects/includes/orphan_work_item_row_edit.html"
        elif context["is_project_epic_children_embed"]:
            display_template = "projects/includes/epic_child_row_embed.html"
            edit_template = "projects/includes/epic_children_row_edit_embed.html"
        elif context["is_project_epics_embed"]:
            display_template = "projects/includes/epic_row_embed.html"
            edit_template = "projects/includes/epic_row_edit_embed.html"
        elif context["is_embed"]:
            display_template = "issues/includes/issue_row_embed.html"
            edit_template = "issues/includes/issue_row_edit_embed.html"
        elif context["is_dashboard"]:
            display_template = "dashboard/includes/dashboard_issue_row.html"
            edit_template = "includes/dashboard_issue_row_edit.html"
        else:
            display_template = "issues/includes/issue_row.html"
            edit_template = "issues/includes/issue_row_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        form = IssueRowInlineEditForm(
            initial={
                "title": real_issue.title,
                "status": real_issue.status,
                "priority": getattr(real_issue, "priority", None),
                "assignee": real_issue.assignee,
                "estimated_points": getattr(real_issue, "estimated_points", None),
            },
            workspace_members=request.workspace_members,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        from django.shortcuts import render

        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        form = IssueRowInlineEditForm(request.POST, workspace_members=request.workspace_members)
        context, real_issue = self._get_context(request, issue, form)

        # Determine template based on context (embed, dashboard, or default)
        if context["is_project_orphan_embed"]:
            display_template = "projects/includes/orphan_work_item_row.html"
            edit_template = "projects/includes/orphan_work_item_row_edit.html"
        elif context["is_project_epic_children_embed"]:
            display_template = "projects/includes/epic_child_row_embed.html"
            edit_template = "projects/includes/epic_children_row_edit_embed.html"
        elif context["is_project_epics_embed"]:
            display_template = "projects/includes/epic_row_embed.html"
            edit_template = "projects/includes/epic_row_edit_embed.html"
        elif context["is_embed"]:
            display_template = "issues/includes/issue_row_embed.html"
            edit_template = "issues/includes/issue_row_edit_embed.html"
        elif context["is_dashboard"]:
            display_template = "dashboard/includes/dashboard_issue_row.html"
            edit_template = "includes/dashboard_issue_row_edit.html"
        else:
            display_template = "issues/includes/issue_row.html"
            edit_template = "issues/includes/issue_row_edit.html"

        if form.is_valid():
            old_status = real_issue.status

            # Update issue fields
            real_issue.title = form.cleaned_data["title"]
            real_issue.status = form.cleaned_data["status"]
            real_issue.assignee = form.cleaned_data.get("assignee")

            # Priority and estimated_points only apply to work items (not Epic base)
            if hasattr(real_issue, "priority") and form.cleaned_data.get("priority"):
                real_issue.priority = form.cleaned_data["priority"]

            if hasattr(real_issue, "estimated_points"):
                real_issue.estimated_points = form.cleaned_data.get("estimated_points")

            real_issue.save()

            # Return display mode
            response = render(request, display_template, context)
            if context["is_dashboard"]:
                response["HX-Trigger-After-Settle"] = "dashboard-updated"

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, real_issue, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


class EpicDetailInlineEditView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Handle inline editing of epic details on the detail page."""

    def _get_context(self, request, epic, form=None):
        """Build common context for GET/POST handlers."""
        milestones = Milestone.objects.for_project(self.project)
        context = {
            "issue": epic,
            "workspace": self.workspace,
            "project": self.project,
            "workspace_members": request.workspace_members,
            "milestones": milestones,
            "milestone": epic.milestone,
            "status_choices": IssueStatus.choices,
            "priority_choices": IssuePriority.choices,
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the epic detail header."""
        from django.shortcuts import render

        epic = get_object_or_404(
            Epic.objects.for_project(self.project).select_related("assignee", "milestone"),
            key=kwargs["key"],
        )
        context = self._get_context(request, epic)

        display_template = "issues/includes/epic_detail_header.html"
        edit_template = "issues/includes/epic_detail_header_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        milestones = context["milestones"]
        form = EpicDetailInlineEditForm(
            initial={
                "title": epic.title,
                "description": epic.description,
                "status": epic.status,
                "priority": epic.priority,
                "assignee": epic.assignee,
                "due_date": epic.due_date,
                "milestone": epic.milestone,
            },
            workspace_members=request.workspace_members,
            milestones=milestones,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        from django.shortcuts import render

        epic = get_object_or_404(
            Epic.objects.for_project(self.project).select_related("assignee", "milestone"),
            key=kwargs["key"],
        )
        milestones = Milestone.objects.for_project(self.project)
        form = EpicDetailInlineEditForm(
            request.POST,
            workspace_members=request.workspace_members,
            milestones=milestones,
        )
        context = self._get_context(request, epic, form)

        display_template = "issues/includes/epic_detail_header.html"
        edit_template = "issues/includes/epic_detail_header_edit.html"

        if form.is_valid():
            old_status = epic.status

            # Update epic fields
            epic.title = form.cleaned_data["title"]
            epic.description = form.cleaned_data.get("description") or ""
            epic.status = form.cleaned_data["status"]
            epic.priority = form.cleaned_data.get("priority") or ""
            epic.assignee = form.cleaned_data.get("assignee")
            epic.due_date = form.cleaned_data.get("due_date")
            epic.milestone = form.cleaned_data.get("milestone")
            epic.save()

            # Refresh milestone in context after save
            context["milestone"] = epic.milestone

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, epic, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)


class IssueDetailInlineEditView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Handle inline editing of non-epic issue details on the detail page."""

    def _get_context(self, request, issue, form=None):
        """Build common context for GET/POST handlers."""
        real_issue = issue.get_real_instance()
        is_bug = isinstance(real_issue, Bug)
        epics = Epic.objects.for_project(self.project)
        parent = real_issue.get_parent_issue()

        context = {
            "issue": real_issue,
            "workspace": self.workspace,
            "project": self.project,
            "workspace_members": request.workspace_members,
            "epics": epics,
            "parent": parent,
            "is_bug": is_bug,
            "status_choices": IssueStatus.choices,
            "priority_choices": IssuePriority.choices,
            "severity_choices": BugSeverity.choices if is_bug else [],
        }
        if form:
            context["form"] = form
        return context

    def get(self, request, *args, **kwargs):
        """Return display mode (cancel=1) or edit mode for the issue detail header."""
        from django.shortcuts import render

        issue = get_object_or_404(
            BaseIssue.objects.for_project(self.project).select_related("assignee"),
            key=kwargs["key"],
        )
        context = self._get_context(request, issue)

        display_template = "issues/includes/issue_detail_header.html"
        edit_template = "issues/includes/issue_detail_header_edit.html"

        # Cancel mode - return display template
        if request.GET.get("cancel") == "1":
            return render(request, display_template, context)

        # Edit mode - return edit template with form
        real_issue = context["issue"]
        epics = context["epics"]
        parent = context["parent"]
        form = IssueDetailInlineEditForm(
            initial={
                "title": real_issue.title,
                "description": real_issue.description,
                "status": real_issue.status,
                "priority": real_issue.priority,
                "assignee": real_issue.assignee,
                "due_date": real_issue.due_date,
                "estimated_points": real_issue.estimated_points,
                "parent": parent,
                "severity": getattr(real_issue, "severity", None),
            },
            workspace_members=request.workspace_members,
            epics=epics,
        )
        context["form"] = form
        return render(request, edit_template, context)

    def post(self, request, *args, **kwargs):
        """Save inline edits and return display mode."""
        from django.shortcuts import render

        issue = get_object_or_404(
            BaseIssue.objects.for_project(self.project).select_related("assignee"),
            key=kwargs["key"],
        )
        epics = Epic.objects.for_project(self.project)
        form = IssueDetailInlineEditForm(
            request.POST,
            workspace_members=request.workspace_members,
            epics=epics,
        )
        context = self._get_context(request, issue, form)

        display_template = "issues/includes/issue_detail_header.html"
        edit_template = "issues/includes/issue_detail_header_edit.html"

        if form.is_valid():
            real_issue = context["issue"]
            old_status = real_issue.status

            # Update issue fields
            real_issue.title = form.cleaned_data["title"]
            real_issue.description = form.cleaned_data.get("description") or ""
            real_issue.status = form.cleaned_data["status"]
            real_issue.priority = form.cleaned_data.get("priority") or ""
            real_issue.assignee = form.cleaned_data.get("assignee")
            real_issue.due_date = form.cleaned_data.get("due_date")
            real_issue.estimated_points = form.cleaned_data.get("estimated_points")

            # Severity only applies to bugs
            if context["is_bug"] and form.cleaned_data.get("severity"):
                real_issue.severity = form.cleaned_data["severity"]

            real_issue.save()

            # Handle parent change (move in tree)
            new_parent = form.cleaned_data.get("parent")
            current_parent = context["parent"]

            if new_parent != current_parent:
                if new_parent is None:
                    # Move to root - use 'last-sibling' to append without path shuffling
                    any_root = BaseIssue.get_first_root_node()
                    if any_root:
                        real_issue.move(any_root, pos="last-sibling")
                else:
                    # Move under new parent
                    real_issue.move(new_parent, pos="last-child")

            # Refresh parent in context after save
            context["parent"] = real_issue.get_parent_issue()

            # Return display mode
            response = render(request, display_template, context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, real_issue, new_status, response)

            return response

        # Validation error - return edit mode with errors
        return render(request, edit_template, context)
