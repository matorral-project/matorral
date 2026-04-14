from collections import OrderedDict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.helpers import calculate_valid_page
from apps.utils.filters import get_status_filter_label, parse_status_filter
from apps.utils.progress import build_progress_dict
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from ..forms import BulkActionForm
from ..models import Project, ProjectStatus
from ..registry import apply_bulk_cascade, build_project_bulk_action_context, project_bulk_actions
from .crud import GROUP_BY_CHOICES
from .mixins import ProjectViewMixin

User = get_user_model()


def _get_redirect_url_with_page(workspace_slug: str, page: int | None) -> str:
    """Build redirect URL for project list, preserving page if valid."""
    url = reverse("projects:project_list", kwargs={"workspace_slug": workspace_slug})
    if page and page > 1:
        url = f"{url}?page={page}"
    return url


class ProjectBulkActionView(ProjectViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Generic dispatch view for all bulk project actions.

    Looks up the action by name from the registry, validates forms, runs
    ``action.validate()``, then ``action.execute()``. Status-changing actions
    stash cascade-eligible objects on the request so the response can be
    wrapped with a cascade OOB payload.
    """

    http_method_names = ["post"]
    form_class = BulkActionForm

    def get_queryset(self):
        return Project.objects.for_workspace(self.workspace)

    def get_selected_queryset(self):
        return self.form.cleaned_data["projects"]

    def _base_form_kwargs(self):
        return {"data": self.request.POST, "queryset": self.get_queryset()}

    def _build_form(self, form_class):
        kwargs = self._base_form_kwargs()
        if form_class is self.form_class:
            return form_class(**kwargs)

        # Extra forms (BulkLeadForm / BulkMoveForm) require additional kwargs
        kwargs["workspace"] = self.workspace
        if "workspace_members" in form_class.__init__.__code__.co_varnames:
            kwargs["workspace_members"] = self.request.workspace_members
        if "user" in form_class.__init__.__code__.co_varnames:
            kwargs["user"] = self.request.user
        return form_class(**kwargs)

    def post(self, request, *args, **kwargs):
        action_name = kwargs["action_name"]
        action = project_bulk_actions.get(action_name)
        if not action:
            raise Http404

        extra_form_class = action.get_form_class()
        form_class = extra_form_class or self.form_class
        self.form = self._build_form(form_class)

        if not self.form.is_valid():
            for errors in self.form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return self.render_response(int(request.POST.get("page", 1)))

        if not self.form.cleaned_data["projects"]:
            messages.warning(request, _("No projects selected."))
            return self.render_response(self.form.cleaned_data["page"])

        selected_qs = self.get_selected_queryset()

        try:
            action.validate(selected_qs, request)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self.render_response(self.form.cleaned_data["page"])

        extra_cleaned_data = self.form.cleaned_data if extra_form_class else None
        try:
            result = action.execute(selected_qs, request, extra_cleaned_data=extra_cleaned_data)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self.render_response(self.form.cleaned_data["page"])

        messages.success(request, result.message)

        page = self.form.cleaned_data["page"]
        redirect_page = (
            calculate_valid_page(result.remaining_count, page) if result.remaining_count is not None else page
        )

        return self.render_response(redirect_page)

    def render_response(self, page):
        if getattr(self.request, "_move_operation_id", None) and self.request.htmx:
            return render(
                self.request,
                "projects/includes/move_progress.html",
                {
                    "operation_id": self.request._move_operation_id,
                    "total": self.request._move_total,
                    "completed": 0,
                    "workspace": self.workspace,
                },
            )

        if not self.request.htmx:
            return redirect(_get_redirect_url_with_page(self.kwargs["workspace_slug"], page))

        context = self._build_list_context(page)
        response = render(self.request, "projects/project_list.html#page-content", context)
        return apply_bulk_cascade(self.request, response)

    def _build_list_context(self, page):
        form = self.form
        search_query = form.cleaned_data.get("search", "")
        status_filter = form.cleaned_data.get("status_filter", "")
        lead_filter = form.cleaned_data.get("lead_filter", "")
        group_by = form.cleaned_data.get("group_by", "")

        queryset = self.get_queryset().search(search_query).select_related("lead", "workspace")
        status_values = parse_status_filter(status_filter, ProjectStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)
        if lead_filter:
            if lead_filter == "none":
                queryset = queryset.filter(lead__isnull=True)
            elif lead_filter.isdigit():
                queryset = queryset.filter(lead_id=int(lead_filter))

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

        base_context = {
            "workspace": self.workspace,
            "active_tab": "projects",
            "status_choices": ProjectStatus.choices,
            "workspace_members": self.request.workspace_members,
            "search_query": search_query,
            "status_filter": status_filter,
            "status_filter_label": get_status_filter_label(status_filter, ProjectStatus.choices),
            "lead_filter": lead_filter,
            "lead_filter_label": lead_filter_label,
            "group_by": group_by,
            "group_by_label": dict(GROUP_BY_CHOICES).get(group_by, "") if group_by else "",
            "group_by_choices": GROUP_BY_CHOICES,
        }
        base_context.update(build_project_bulk_action_context(self.workspace))

        if group_by:
            projects = list(queryset.with_progress())
            self._annotate_progress(projects)
            base_context.update(
                {
                    "projects": projects,
                    "is_paginated": False,
                    "grouped_projects": self._build_grouped_projects(projects, group_by),
                }
            )
            return base_context

        paginator = Paginator(queryset.with_progress(), settings.DEFAULT_PAGE_SIZE)
        page_obj = paginator.get_page(page or 1)
        self._annotate_progress(page_obj)
        base_context.update(
            {
                "projects": page_obj,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": page_obj.has_other_pages(),
            }
        )
        if base_context["is_paginated"]:
            base_context["elided_page_range"] = paginator.get_elided_page_range(
                page_obj.number, on_each_side=2, on_ends=1
            )
        return base_context

    @staticmethod
    def _annotate_progress(projects):
        for project in projects:
            total = getattr(project, "total_estimated_points", 0) or 0
            done = getattr(project, "total_done_points", 0) or 0
            in_progress = getattr(project, "total_in_progress_points", 0) or 0
            todo = getattr(project, "total_todo_points", 0) or 0
            project.progress = build_progress_dict(done, in_progress, todo, total)

    @staticmethod
    def _build_grouped_projects(projects, group_by):
        grouped = OrderedDict()
        if group_by == "status":
            status_labels = dict(ProjectStatus.choices)
            for project in projects:
                group_name = status_labels.get(project.status, project.status)
                grouped.setdefault(group_name, []).append(project)
        elif group_by == "lead":
            for project in projects:
                group_name = project.lead.get_display_name() if project.lead else str(_("No lead"))
                grouped.setdefault(group_name, []).append(project)
        return grouped
