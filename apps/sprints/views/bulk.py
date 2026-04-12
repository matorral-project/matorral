from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.helpers import calculate_valid_page
from apps.sprints.forms import SprintBulkActionForm
from apps.sprints.models import Sprint
from apps.sprints.registry import build_sprint_bulk_action_context, sprint_bulk_actions
from apps.sprints.views.mixins import SprintListContextMixin, SprintViewMixin
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin


def _get_sprint_redirect_url(workspace_slug: str, page: int | None) -> str:
    """Build redirect URL for sprint list, preserving page if valid."""
    url = reverse("sprints:sprint_list", kwargs={"workspace_slug": workspace_slug})
    if page and page > 1:
        url = f"{url}?page={page}"
    return url


class SprintBulkActionMixin(SprintViewMixin, SprintListContextMixin):
    """Base mixin for bulk operations on sprints."""

    http_method_names = ["post"]
    form_class = SprintBulkActionForm

    def get_queryset(self):
        return Sprint.objects.for_workspace(self.workspace)

    def get_selected_queryset(self):
        """Return the selected sprints from form's cleaned data.

        ModelMultipleChoiceField returns model instances directly, so we can use them as a queryset.
        """
        return self.form.cleaned_data["sprints"]

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "workspace": self.workspace,
        }

    def get_form(self):
        return self.form_class(**self.get_form_kwargs())

    def render_response(self, page):
        if not self.request.htmx:
            return redirect(
                _get_sprint_redirect_url(
                    self.kwargs["workspace_slug"],
                    page,
                )
            )

        # Render the sprint list template for HTMX bulk operations
        search_query = self.form.cleaned_data.get("search", "")
        status_filter = self.form.cleaned_data.get("status_filter", "")
        owner_filter = self.form.cleaned_data.get("owner_filter", "")

        queryset = self.get_queryset().select_related("workspace", "owner").with_progress()
        queryset = self.apply_sprint_filters(queryset, search_query, status_filter, owner_filter)

        paginator = Paginator(queryset, settings.DEFAULT_PAGE_SIZE)
        page_obj = paginator.get_page(page or 1)

        context = self.get_sprint_list_context(search_query, status_filter, owner_filter)
        context.update(build_sprint_bulk_action_context(self.workspace))
        context.update(
            {
                "sprints": page_obj,
                "page_obj": page_obj,
                "paginator": paginator,
                "is_paginated": page_obj.has_other_pages(),
            }
        )

        if context["is_paginated"]:
            context["elided_page_range"] = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)

        return render(self.request, "sprints/sprint_list.html#page-content", context)


class SprintBulkActionView(SprintBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Generic dispatch view for all bulk sprint actions.

    Looks up the action by name from the registry, validates forms,
    runs action.validate(), then action.execute().
    """

    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        action_name = kwargs["action_name"]
        action = sprint_bulk_actions.get(action_name)
        if not action:
            raise Http404

        # Handle extra form for actions that need one (e.g., owner picker)
        extra_form_class = action.get_form_class()
        if extra_form_class:
            self.form = extra_form_class(
                data=request.POST,
                workspace=self.workspace,
                workspace_members=request.workspace_members,
            )
        else:
            self.form = self.get_form()

        if not self.form.is_valid():
            for errors in self.form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return self.render_response(int(request.POST.get("page", 1)))

        if not self.form.cleaned_data["sprints"]:
            messages.warning(request, _("No sprints selected."))
            return self.render_response(self.form.cleaned_data["page"])

        selected_qs = self.get_selected_queryset()

        # Run action validation
        try:
            action.validate(selected_qs, request)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self.render_response(self.form.cleaned_data["page"])

        # Execute the action
        try:
            result = action.execute(selected_qs, request)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self.render_response(self.form.cleaned_data["page"])

        # BulkDeleteAction returns (deleted_count, remaining_count) for page calculation
        if isinstance(result, tuple):
            _deleted_count, remaining_count = result
            messages.success(
                request,
                _("%(count)d sprint(s) deleted successfully.") % {"count": _deleted_count},
            )
            redirect_page = calculate_valid_page(remaining_count, self.form.cleaned_data["page"])
        else:
            messages.success(request, result)
            redirect_page = self.form.cleaned_data["page"]

        return self.render_response(redirect_page)


class SprintBulkActionConfirmView(SprintBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Render confirmation modal for bulk actions with confirm=True."""

    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        action_name = kwargs["action_name"]
        action = sprint_bulk_actions.get(action_name)
        if not action or not action.confirm:
            raise Http404

        return render(
            request,
            "sprints/includes/bulk_action_confirm_modal.html",
            {
                "action": action,
                "post_url": action.get_url(self.workspace),
            },
        )
