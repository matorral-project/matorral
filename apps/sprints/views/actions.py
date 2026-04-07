from django.contrib import messages
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin

from apps.issues.models import BaseIssue, IssueStatus
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.registry import sprint_actions
from apps.sprints.views.mixins import SprintSingleObjectMixin, SprintViewMixin
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from django_htmx.http import HttpResponseClientRedirect


class SprintActionMixin(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, SingleObjectMixin):
    """Shared lookup for action + sprint, with availability check."""

    def get_action_and_sprint(self, action_name):
        action = sprint_actions.get(action_name)
        if action is None:
            raise Http404

        sprint = self.get_object()

        if not action.is_available(sprint, self.request.user):
            raise Http404

        return action, sprint


class SprintActionConfirmView(SprintActionMixin, View):
    """GET — returns confirmation modal HTML for an action."""

    def get(self, request, action_name, **kwargs):
        action, sprint = self.get_action_and_sprint(action_name)
        return action.get_confirm_response(sprint, request)


class SprintActionView(SprintActionMixin, View):
    """POST — executes a registered sprint action."""

    def post(self, request, action_name, **kwargs):
        action, sprint = self.get_action_and_sprint(action_name)
        return action.execute(sprint, request)


class SprintAddIssuesView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, View):
    """Modal to search and add issues to a sprint."""

    template_name = "sprints/includes/add_issues_modal_content.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])

    def get_unassigned_issues(self, search_query: str = ""):
        """Get work items in workspace not assigned to any sprint (excludes archived and done)."""
        qs = (
            BaseIssue.objects.for_workspace(self.workspace)
            .backlog()
            .exclude(status__in=[IssueStatus.ARCHIVED, IssueStatus.DONE])
            .select_related("project", "assignee")
        )

        if search_query:
            qs = qs.filter(title__icontains=search_query) | qs.filter(key__icontains=search_query)

        return qs[:50]

    def get(self, request, *args, **kwargs):
        search_query = request.GET.get("search", "").strip()
        issues = self.get_unassigned_issues(search_query)

        context = {
            "workspace": self.workspace,
            "sprint": self.sprint,
            "issues": issues,
            "search_query": search_query,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        issue_keys = request.POST.getlist("issues")
        if not issue_keys:
            messages.warning(request, _("No issues selected."))
            return redirect(self.sprint.get_absolute_url())

        added_count = self.sprint.add_issues(issue_keys, self.workspace)

        if added_count > 0:
            messages.success(
                request,
                _("%(count)d issue(s) added to sprint.") % {"count": added_count},
            )
        else:
            messages.warning(request, _("No issues were added."))

        # Return the embedded issues list for HTMX
        if request.htmx:
            return HttpResponseRedirect(
                reverse(
                    "sprints:sprint_issues_embed",
                    kwargs={
                        "workspace_slug": self.kwargs["workspace_slug"],
                        "key": self.sprint.key,
                    },
                )
            )

        return redirect(self.sprint.get_absolute_url())


class SprintRemoveIssueView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Remove an issue from a sprint."""

    def post(self, request, *args, **kwargs):
        sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])
        issue_key = kwargs["issue_key"]

        removed = sprint.remove_issue(issue_key)

        if removed:
            messages.success(request, _("Issue removed from sprint."))
        else:
            messages.warning(request, _("Issue not found in this sprint."))

        # Check for custom redirect URL (e.g., from issue detail page)
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and request.htmx:
            return HttpResponseClientRedirect(next_url)

        # Return the embedded issues list for HTMX (default behavior for sprint page)
        if request.htmx:
            return HttpResponseRedirect(
                reverse(
                    "sprints:sprint_issues_embed",
                    kwargs={
                        "workspace_slug": self.kwargs["workspace_slug"],
                        "key": sprint.key,
                    },
                )
            )

        return redirect(next_url or sprint.get_absolute_url())


class IssueAddToSprintView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Modal to add a single issue to a sprint (from issue row 3-dots menu)."""

    template_name = "sprints/includes/add_to_sprint_modal.html"

    def get_issue(self, issue_key: str):
        """Find the issue by key across all work item types."""
        return (
            BaseIssue.objects.for_workspace(self.workspace)
            .work_items()
            .filter(key=issue_key)
            .select_related("project")
            .first()
        )

    def get(self, request, *args, **kwargs):
        issue_key = kwargs["issue_key"]
        issue = self.get_issue(issue_key)

        if not issue:
            messages.error(request, _("Issue not found."))
            return render(
                request,
                self.template_name,
                {"workspace": self.workspace, "issue": None},
            )

        # Get available sprints (planning or active only)
        sprints = list(Sprint.objects.for_workspace(self.workspace).available())

        # Determine the sprint to pre-select: current sprint > active sprint > first sprint
        if issue.sprint:
            default_sprint = issue.sprint
        else:
            default_sprint = next((s for s in sprints if s.status == SprintStatus.ACTIVE), None)
            if default_sprint is None and sprints:
                default_sprint = sprints[0]

        context = {
            "workspace": self.workspace,
            "issue": issue,
            "sprints": sprints,
            "current_sprint": issue.sprint,
            "default_sprint": default_sprint,
        }
        return render(request, self.template_name, context)


class IssueAddToSprintConfirmView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, View):
    """Confirm adding a single issue to a sprint."""

    def post(self, request, *args, **kwargs):
        issue_key = kwargs["issue_key"]
        sprint_key = request.POST.get("sprint")

        # Find the issue
        issue = BaseIssue.objects.for_workspace(self.workspace).work_items().filter(key=issue_key).first()

        if not issue:
            messages.error(request, _("Issue not found."))
            return redirect("workspace_issue_list", workspace_slug=self.workspace.slug)

        # Find the sprint
        sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace).not_archived(), key=sprint_key)

        # Update the issue's sprint
        issue.sprint = sprint
        issue.save(update_fields=["sprint", "updated_at"])

        messages.success(
            request,
            _("Issue %(issue)s added to %(sprint)s.") % {"issue": issue.key, "sprint": sprint.name},
        )

        if request.htmx:
            response = render(request, "includes/messages.html")
            response["HX-Trigger"] = '{"issueChanged": true}'
            return response

        next_url = request.POST.get("next") or request.GET.get("next")
        return redirect(next_url or issue.get_absolute_url())
