from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from apps.sprints.models import Sprint, SprintStatus
from apps.utils.filters import build_filter_section, count_active_filters, get_status_filter_label, parse_status_filter
from apps.workspaces.models import Workspace

User = get_user_model()


class SprintViewMixin:
    """Base mixin for all sprint views.

    IMPORTANT: This mixin must override get_queryset() to use workspace-scoped filtering.
    """

    model = Sprint

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.workspace = get_object_or_404(Workspace.objects, slug=kwargs["workspace_slug"])

    def get_queryset(self):
        """Override get_queryset() to use workspace-scoped filtering."""
        return Sprint.objects.for_workspace(self.workspace)

    def get_template_names(self):
        if self.request.htmx:
            return [f"{self.template_name}#page-content"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["workspace"] = self.workspace
        return context


class SprintListContextMixin:
    """Shared filtering and context logic for sprint list views."""

    def apply_sprint_filters(self, queryset, search_query: str, status_filter: str, owner_filter: str):
        """Apply search, status, and owner filters to a sprint queryset."""
        if search_query:
            queryset = queryset.search(search_query)

        status_values = parse_status_filter(status_filter, SprintStatus.choices)
        if status_values:
            queryset = queryset.filter(status__in=status_values)

        if owner_filter:
            if owner_filter == "unassigned":
                queryset = queryset.filter(owner__isnull=True)
            else:
                queryset = queryset.filter(owner_id=owner_filter)

        return queryset.order_by("-start_date", "name")

    def get_owner_filter_label(self, owner_filter: str, workspace_members):
        """Get the display label for the owner filter."""
        if owner_filter and owner_filter != "unassigned":
            try:
                selected_owner = workspace_members.get(pk=owner_filter)
                return selected_owner.get_display_name()
            except User.DoesNotExist:
                return ""
        elif owner_filter == "unassigned":
            return _("Unassigned")
        return ""

    def get_sprint_list_context(
        self,
        search_query: str,
        status_filter: str,
        owner_filter: str,
        using_default_status_filter: bool = False,
    ):
        """Build common context for sprint list views."""
        workspace_members = self.request.workspace_members

        # Build owner choices from workspace members
        owner_choices = [("unassigned", _("Unassigned"))]
        for member in workspace_members:
            owner_choices.append((str(member.pk), member.get_display_name()))

        # Build filter sections for modal
        filter_sections = [
            build_filter_section(
                name="status",
                label=_("Status"),
                filter_type="multi_select",
                choices=SprintStatus.choices,
                current_value=status_filter,
            ),
            build_filter_section(
                name="owner",
                label=_("Owner"),
                filter_type="single_select",
                choices=owner_choices,
                current_value=owner_filter,
                empty_label=_("All"),
            ),
        ]

        # Count active filters (includes default status filter)
        active_filters = {"status": status_filter, "owner": owner_filter}
        active_filter_count = count_active_filters(active_filters)

        return {
            "workspace": self.workspace,
            "status_choices": SprintStatus.choices,
            "workspace_members": workspace_members,
            "search_query": search_query,
            "status_filter": status_filter,
            "status_filter_label": get_status_filter_label(status_filter, SprintStatus.choices),
            "owner_filter": owner_filter,
            "owner_filter_label": self.get_owner_filter_label(owner_filter, workspace_members),
            "filter_sections": filter_sections,
            "active_filter_count": active_filter_count,
            "using_default_status_filter": using_default_status_filter,
        }


class SprintSingleObjectMixin:
    """Mixin for views that operate on a single sprint."""

    context_object_name = "sprint"
    slug_field = "key"
    slug_url_kwarg = "key"


class SprintFormMixin:
    """Mixin for views with sprint forms."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["workspace"] = self.workspace
        kwargs["workspace_members"] = self.request.workspace_members
        return kwargs
