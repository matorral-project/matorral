from django.contrib import messages
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.models import BaseIssue, Bug, Chore, IssueStatus, Story
from apps.sprints.models import Sprint, SprintStatus
from apps.sprints.views.mixins import SprintSingleObjectMixin, SprintViewMixin
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from django_htmx.http import HttpResponseClientRedirect


class SprintStartView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, View):
    """Start a sprint (change status to active)."""

    def post(self, request, *args, **kwargs):
        sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])

        if not sprint.can_start():
            if sprint.status != SprintStatus.PLANNING:
                messages.error(request, _("Only sprints in planning status can be started."))
            else:
                messages.error(request, _("Another sprint is already active in this workspace."))
            return redirect(sprint.get_absolute_url())

        # Capture committed points at sprint start
        sprint.committed_points = sprint.calculate_committed_points()
        sprint.status = SprintStatus.ACTIVE

        try:
            sprint.save(update_fields=["status", "committed_points", "updated_at"])
            messages.success(request, _("Sprint started successfully."))
        except IntegrityError:
            messages.error(request, _("Another sprint is already active in this workspace."))

        return redirect(sprint.get_absolute_url())


class SprintCompleteView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, View):
    """Complete a sprint and optionally move incomplete issues to next sprint."""

    def post(self, request, *args, **kwargs):
        sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])

        if sprint.status != SprintStatus.ACTIVE:
            messages.error(request, _("Only active sprints can be completed."))
            return redirect(sprint.get_absolute_url())

        # Calculate completed points
        sprint.completed_points = sprint.calculate_completed_points()
        sprint.status = SprintStatus.COMPLETED
        sprint.save(update_fields=["status", "completed_points", "updated_at"])

        # Move incomplete issues to next sprint if available
        next_sprint = sprint.get_next_sprint()
        moved_count = 0
        if next_sprint:
            incomplete_statuses = [
                IssueStatus.DRAFT,
                IssueStatus.PLANNING,
                IssueStatus.READY,
                IssueStatus.IN_PROGRESS,
                IssueStatus.BLOCKED,
            ]
            for model in [Story, Bug, Chore]:
                count = model.objects.filter(sprint=sprint, status__in=incomplete_statuses).update(sprint=next_sprint)
                moved_count += count

        if moved_count > 0:
            messages.success(
                request,
                _("Sprint completed. %(count)d incomplete issue(s) moved to %(sprint)s.")
                % {"count": moved_count, "sprint": next_sprint.name},
            )
        else:
            messages.success(request, _("Sprint completed successfully."))

        return redirect(sprint.get_absolute_url())


class SprintArchiveView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, View):
    """Archive a sprint (must not be active)."""

    def post(self, request, *args, **kwargs):
        sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])

        if sprint.status == SprintStatus.ACTIVE:
            messages.error(
                request,
                _("Active sprints cannot be archived. Complete the sprint first."),
            )
            return redirect(sprint.get_absolute_url())

        sprint.status = SprintStatus.ARCHIVED
        sprint.save(update_fields=["status", "updated_at"])
        messages.success(request, _("Sprint archived successfully."))
        return redirect(sprint.get_absolute_url())


class SprintAddIssuesView(SprintViewMixin, LoginAndWorkspaceRequiredMixin, SprintSingleObjectMixin, View):
    """Modal to search and add issues to a sprint."""

    template_name = "sprints/includes/add_issues_modal_content.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.sprint = get_object_or_404(Sprint.objects.for_workspace(self.workspace), key=kwargs["key"])

    def get_unassigned_issues(self, search_query: str = ""):
        """Get work items in workspace not assigned to any sprint (excludes archived and done)."""
        # Get active work items without a sprint assignment
        unassigned = []
        for model in [Story, Bug, Chore]:
            qs = (
                model.objects.filter(project__workspace=self.workspace, sprint__isnull=True)
                .exclude(status__in=[IssueStatus.ARCHIVED, IssueStatus.DONE])
                .select_related("project", "assignee")
            )
            if search_query:
                qs = qs.filter(title__icontains=search_query) | qs.filter(key__icontains=search_query)
            unassigned.extend(qs[:50])  # Limit results

        return unassigned

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

        # Add issues to sprint
        added_count = 0
        for model in [Story, Bug, Chore]:
            count = model.objects.filter(
                project__workspace=self.workspace,
                key__in=issue_keys,
                sprint__isnull=True,
            ).update(sprint=self.sprint)
            added_count += count

        if added_count > 0:
            messages.success(
                request,
                _("%(count)d issue(s) added to sprint.") % {"count": added_count},
            )
        else:
            messages.warning(request, _("No issues were added."))

        # Return the embedded issues list for HTMX
        if request.htmx:
            from django.http import HttpResponseRedirect
            from django.urls import reverse

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

        # Find and update the issue
        removed = False
        for model in [Story, Bug, Chore]:
            count = model.objects.filter(sprint=sprint, key=issue_key).update(sprint=None)
            if count > 0:
                removed = True
                break

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
            from django.http import HttpResponseRedirect
            from django.urls import reverse

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
        sprints = list(
            Sprint.objects.for_workspace(self.workspace)
            .filter(status__in=[SprintStatus.PLANNING, SprintStatus.ACTIVE])
            .order_by("-status", "-start_date")
        )

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
