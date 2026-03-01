from collections import OrderedDict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.cascade import build_cascade_oob_response_bulk
from apps.utils.audit import bulk_create_audit_logs
from apps.utils.filters import get_status_filter_label, parse_status_filter
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from ..forms import BulkActionForm, BulkLeadForm, BulkMoveForm
from ..models import Project, ProjectStatus
from ..tasks import move_project_task
from .crud import GROUP_BY_CHOICES, _attach_progress_to_projects
from .mixins import ProjectViewMixin

User = get_user_model()


def _get_redirect_url_with_page(workspace_slug: str, page: int | None) -> str:
    """Build redirect URL for project list, preserving page if valid."""
    url = reverse(
        "projects:project_list",
        kwargs={"workspace_slug": workspace_slug},
    )
    if page and page > 1:
        url = f"{url}?page={page}"
    return url


def _calculate_valid_page(
    total_count: int, current_page: int, per_page: int = settings.DEFAULT_PAGE_SIZE
) -> int | None:
    """Calculate the valid page to redirect to after items are removed."""
    if total_count == 0:
        return None

    total_pages = (total_count + per_page - 1) // per_page
    return min(current_page, total_pages)


class BulkActionMixin(ProjectViewMixin):
    """Base mixin for bulk operations on projects."""

    http_method_names = ["post"]
    form_class = BulkActionForm

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace)

    def get_selected_queryset(self):
        # ModelMultipleChoiceField returns a queryset of selected objects
        return self.form.cleaned_data["projects"]

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

        if not self.form.cleaned_data["projects"]:
            messages.warning(request, _("No projects selected."))
            return self.render_response(self.form.cleaned_data["page"])

        redirect_page = self.perform_action()
        return self.render_response(redirect_page)

    def perform_action(self):
        """Subclasses implement this. Returns the page to redirect to."""
        raise NotImplementedError

    def render_response(self, page):
        if not self.request.htmx:
            return redirect(_get_redirect_url_with_page(self.kwargs["workspace_slug"], page))

        """Render the project list template for HTMX bulk operations."""
        search_query = self.form.cleaned_data.get("search", "")
        status_filter = self.form.cleaned_data.get("status_filter", "")
        lead_filter = self.form.cleaned_data.get("lead_filter", "")
        group_by = self.form.cleaned_data.get("group_by", "")

        queryset = self.get_queryset().search(search_query).select_related("lead", "workspace")
        status_values = parse_status_filter(status_filter, ProjectStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)
        if lead_filter:
            if lead_filter == "none":
                queryset = queryset.filter(lead__isnull=True)
            elif lead_filter.isdigit():
                queryset = queryset.filter(lead_id=int(lead_filter))

        # Apply ordering based on grouping
        if group_by == "status":
            queryset = queryset.order_by("status", "name")
        elif group_by == "lead":
            queryset = queryset.order_by("lead__first_name", "lead__last_name", "name")

        lead_filter_label = ""
        if lead_filter == "none":
            lead_filter_label = _("No lead")
        elif lead_filter.isdigit():
            lead_id = int(lead_filter)
            for member in self.request.workspace_members:
                if member.pk == lead_id:
                    lead_filter_label = member.get_display_name()
                    break

        # Handle pagination based on grouping
        if group_by:
            projects = list(queryset)
            _attach_progress_to_projects(projects)
            context = {
                "workspace": self.workspace,
                "projects": projects,
                "is_paginated": False,
                "active_tab": "projects",
                "status_choices": ProjectStatus.choices,
                "workspace_members": self.request.workspace_members,
                "search_query": search_query,
                "status_filter": status_filter,
                "status_filter_label": get_status_filter_label(status_filter, ProjectStatus.choices),
                "lead_filter": lead_filter,
                "lead_filter_label": lead_filter_label,
                "group_by": group_by,
                "group_by_label": dict(GROUP_BY_CHOICES).get(group_by, ""),
                "group_by_choices": GROUP_BY_CHOICES,
                "grouped_projects": self._build_grouped_projects(projects, group_by),
            }
        else:
            paginator = Paginator(queryset, settings.DEFAULT_PAGE_SIZE)
            page_obj = paginator.get_page(page or 1)
            _attach_progress_to_projects(list(page_obj))
            context = {
                "workspace": self.workspace,
                "projects": page_obj,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": page_obj.has_other_pages(),
                "active_tab": "projects",
                "status_choices": ProjectStatus.choices,
                "workspace_members": self.request.workspace_members,
                "search_query": search_query,
                "status_filter": status_filter,
                "status_filter_label": get_status_filter_label(status_filter, ProjectStatus.choices),
                "lead_filter": lead_filter,
                "lead_filter_label": lead_filter_label,
                "group_by": group_by,
                "group_by_label": "",
                "group_by_choices": GROUP_BY_CHOICES,
            }
            if context["is_paginated"]:
                context["elided_page_range"] = paginator.get_elided_page_range(
                    page_obj.number, on_each_side=2, on_ends=1
                )

        return render(self.request, "projects/project_list.html#page-content", context)

    def _build_grouped_projects(self, projects, group_by):
        """Build a dictionary of projects grouped by the selected field."""
        grouped = OrderedDict()
        if group_by == "status":
            status_labels = dict(ProjectStatus.choices)
            for project in projects:
                group_name = status_labels.get(project.status, project.status)
                if group_name not in grouped:
                    grouped[group_name] = []
                grouped[group_name].append(project)
        elif group_by == "lead":
            for project in projects:
                group_name = project.lead.get_display_name() if project.lead else str(_("No lead"))
                if group_name not in grouped:
                    grouped[group_name] = []
                grouped[group_name].append(project)
        return grouped


class ProjectBulkDeleteView(BulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Delete multiple projects at once."""

    def perform_action(self):
        deleted_count, _deleted_objects = self.get_selected_queryset().delete()
        messages.success(
            self.request,
            _("%(count)d project(s) deleted successfully.") % {"count": deleted_count},
        )
        remaining_count = self.get_queryset().search(self.form.cleaned_data["search"]).count()
        return _calculate_valid_page(remaining_count, self.form.cleaned_data["page"])


class ProjectBulkStatusView(BulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the status of multiple projects at once."""

    def post(self, request, *args, **kwargs):
        self.status = request.POST.get("status")
        self._cascade_objects = []
        if self.status not in [choice[0] for choice in ProjectStatus.choices]:
            messages.error(request, _("Invalid status value."))
            self.form = self.get_form()
            self.form.is_valid()  # Populate cleaned_data for render_response
            return self.render_response(self.form.cleaned_data.get("page", 1))
        return super().post(request, *args, **kwargs)

    def perform_action(self):
        selected_qs = self.get_selected_queryset()
        status_choices = dict(ProjectStatus.choices)
        objects = list(selected_qs)
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in objects}
        new_display = status_choices.get(self.status, self.status)

        # Save objects snapshot before update for cascade check
        self._cascade_objects = objects

        updated_count = selected_qs.update(status=self.status)
        bulk_create_audit_logs(objects, "status", old_values, new_display, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d project(s) updated to %(status)s.") % {"count": updated_count, "status": new_display},
        )
        return self.form.cleaned_data["page"]

    def render_response(self, page):
        response = super().render_response(page)
        if getattr(self, "_cascade_objects", None) and self.request.htmx:
            response = build_cascade_oob_response_bulk(self.request, self._cascade_objects, self.status, response)
        return response


class ProjectBulkLeadView(BulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the lead of multiple projects at once."""

    form_class = BulkLeadForm

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "queryset": self.get_queryset(),
            "workspace": self.workspace,
            "workspace_members": self.request.workspace_members,
        }

    def perform_action(self):
        lead = self.form.cleaned_data["lead"]
        selected_qs = self.get_selected_queryset()
        objects = list(selected_qs.select_related("lead"))
        old_values = {obj.pk: obj.lead.get_display_name() if obj.lead else None for obj in objects}
        new_display = lead.get_display_name() if lead else None

        updated_count = selected_qs.update(lead=lead)
        bulk_create_audit_logs(objects, "lead", old_values, new_display, actor=self.request.user)

        if lead:
            messages.success(
                self.request,
                _("%(count)d project(s) assigned to %(lead)s.") % {"count": updated_count, "lead": new_display},
            )
        else:
            messages.success(
                self.request,
                _("%(count)d project(s) lead removed.") % {"count": updated_count},
            )
        return self.form.cleaned_data["page"]


class ProjectBulkMoveView(BulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Move multiple projects to another workspace."""

    form_class = BulkMoveForm

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "queryset": self.get_queryset(),
            "workspace": self.workspace,
            "user": self.request.user,
        }

    def perform_action(self):
        target_workspace = self.form.cleaned_data["workspace"]
        selected_qs = self.get_selected_queryset()
        count = selected_qs.count()
        for project in selected_qs:
            move_project_task.delay(project.pk, target_workspace.pk)
        messages.success(
            self.request,
            _("%(count)d project(s) are being moved to %(workspace)s.")
            % {"count": count, "workspace": target_workspace.name},
        )
        return self.form.cleaned_data["page"]
