from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.helpers import calculate_valid_page
from apps.sprints.forms import SprintBulkActionForm, SprintBulkOwnerForm
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.views.mixins import SprintListContextMixin, SprintViewMixin
from apps.utils.audit import bulk_create_audit_logs
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

    def post(self, request, *args, **kwargs):
        self.form = self.get_form()
        if not self.form.is_valid():
            for errors in self.form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return self.render_response(int(request.POST.get("page", 1)))

        if not self.form.cleaned_data["sprints"]:
            messages.warning(request, _("No sprints selected."))
            return self.render_response(self.form.cleaned_data["page"])

        redirect_page = self.perform_action()
        return self.render_response(redirect_page)

    def perform_action(self):
        """Subclasses implement this. Returns the page to redirect to."""
        raise NotImplementedError

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

        queryset = self.get_queryset().select_related("workspace", "owner")
        queryset = self.apply_sprint_filters(queryset, search_query, status_filter, owner_filter)

        paginator = Paginator(queryset, settings.DEFAULT_PAGE_SIZE)
        page_obj = paginator.get_page(page or 1)

        context = self.get_sprint_list_context(search_query, status_filter, owner_filter)
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


class SprintBulkDeleteView(SprintBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Delete multiple sprints at once."""

    def perform_action(self):
        deleted_count, _deleted_objects = self.get_selected_queryset().delete()
        messages.success(
            self.request,
            _("%(count)d sprint(s) deleted successfully.") % {"count": deleted_count},
        )
        remaining_count = self.get_queryset().count()
        return calculate_valid_page(remaining_count, self.form.cleaned_data["page"])


class SprintBulkStatusView(SprintBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the status of multiple sprints at once."""

    def post(self, request, *args, **kwargs):
        self.status = request.POST.get("status")
        if self.status not in [choice[0] for choice in SprintStatus.choices]:
            messages.error(request, _("Invalid status value."))
            self.form = self.get_form()
            self.form.is_valid()
            return self.render_response(self.form.cleaned_data.get("page", 1))
        return super().post(request, *args, **kwargs)

    def perform_action(self):
        selected_pks = list(self.get_selected_queryset().values_list("pk", flat=True))
        selected_sprints = list(Sprint.objects.filter(pk__in=selected_pks))

        # Special handling for "active" status
        if self.status == SprintStatus.ACTIVE:
            if len(selected_sprints) > 1:
                messages.error(
                    self.request,
                    _("Only one sprint can be active at a time. Please select a single sprint to activate."),
                )
                return self.form.cleaned_data["page"]

            # For a single sprint, check if it can be started
            sprint = selected_sprints[0]
            if not sprint.can_start():
                if sprint.status != SprintStatus.PLANNING:
                    messages.error(
                        self.request,
                        _("Sprint '%(name)s' must be in Planning status to be started.") % {"name": sprint.name},
                    )
                else:
                    messages.error(
                        self.request,
                        _("Cannot activate sprint '%(name)s'. Another sprint is already active in this workspace.")
                        % {"name": sprint.name},
                    )
                return self.form.cleaned_data["page"]

            # Activate the single sprint using save() to trigger model validation
            sprint.status = SprintStatus.ACTIVE
            sprint.save()
            messages.success(
                self.request,
                _("Sprint '%(name)s' is now active.") % {"name": sprint.name},
            )
            return self.form.cleaned_data["page"]

        # For other statuses, we can use bulk update
        selected_qs = self.get_selected_queryset()
        status_choices = dict(SprintStatus.choices)
        old_values = {obj.pk: status_choices.get(obj.status, obj.status) for obj in selected_sprints}
        new_display = status_choices.get(self.status, self.status)

        updated_count = selected_qs.update(status=self.status)
        bulk_create_audit_logs(selected_sprints, "status", old_values, new_display, actor=self.request.user)

        messages.success(
            self.request,
            _("%(count)d sprint(s) updated to %(status)s.") % {"count": updated_count, "status": new_display},
        )
        return self.form.cleaned_data["page"]


class SprintBulkOwnerView(SprintBulkActionMixin, LoginAndWorkspaceRequiredMixin, View):
    """Update the owner of multiple sprints at once."""

    form_class = SprintBulkOwnerForm

    def get_form_kwargs(self):
        return {
            "data": self.request.POST,
            "workspace": self.workspace,
            "workspace_members": self.request.workspace_members,
        }

    def perform_action(self):
        owner = self.form.cleaned_data["owner"]
        selected_qs = self.get_selected_queryset()
        selected_pks = list(selected_qs.values_list("pk", flat=True))
        objects = list(Sprint.objects.filter(pk__in=selected_pks).select_related("owner"))
        old_values = {obj.pk: obj.owner.get_display_name() if obj.owner else None for obj in objects}
        new_display = owner.get_display_name() if owner else None

        updated_count = selected_qs.update(owner=owner)
        bulk_create_audit_logs(objects, "owner", old_values, new_display, actor=self.request.user)

        if owner:
            messages.success(
                self.request,
                _("%(count)d sprint(s) assigned to %(owner)s.") % {"count": updated_count, "owner": new_display},
            )
        else:
            messages.success(
                self.request,
                _("%(count)d sprint(s) unassigned.") % {"count": updated_count},
            )
        return self.form.cleaned_data["page"]
