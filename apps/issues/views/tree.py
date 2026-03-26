from itertools import groupby

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from apps.issues.models import BaseIssue, Bug, Chore, Epic, Milestone, Story
from apps.projects.models import Project
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

from django_htmx.http import HttpResponseClientRedirect, HttpResponseClientRefresh

from .mixins import IssueViewMixin


class IssueChildrenView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """HTMX view for lazy-loading issue children."""

    def get(self, request, *args, **kwargs):
        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        children = issue.get_children_issues()
        context = {
            "children": children,
            "workspace": self.workspace,
            "project": self.project,
            "parent": issue,
            "depth": issue.depth + 1,
        }
        return render(request, "issues/includes/issue_children.html", context)


class IssueMoveView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Move an issue to a new parent."""

    def get(self, request, *args, **kwargs):
        """Return the modal content with valid parent options."""
        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])

        # Determine valid parents based on issue type
        grouped_parents = []
        if isinstance(issue, Epic):
            # Epics cannot be moved to have a parent
            valid_parents = Epic.objects.none()
        elif isinstance(issue, (Story, Bug, Chore)):
            # Can only have Epic parents (excluding self)
            valid_parents = (
                Epic.objects.for_project(self.project)
                .exclude(pk=issue.pk)
                .select_related("project", "project__workspace")
                .ordered_by_key()
            )
            # Group epics by milestone parent (tree-based), milestones ordered by key asc, no-milestone last
            epics_list = list(valid_parents)
            steplen = BaseIssue.steplen
            parent_paths = {e.path[:-steplen] for e in epics_list if len(e.path) > steplen}
            milestones_by_path = {}
            if parent_paths:
                for m in Milestone.objects.filter(path__in=parent_paths):
                    milestones_by_path[m.path] = m

            # Sort by milestone key, then orphans last
            with_milestone = [
                (milestones_by_path[e.path[:-steplen]], e)
                for e in epics_list
                if milestones_by_path.get(e.path[:-steplen])
            ]
            without_milestone = [
                e for e in epics_list if not milestones_by_path.get(e.path[:-steplen] if len(e.path) > steplen else "")
            ]

            with_milestone.sort(key=lambda pair: pair[0].key)
            for milestone, group in groupby(with_milestone, key=lambda pair: pair[0]):
                grouped_parents.append((milestone, [pair[1] for pair in group]))

            if without_milestone:
                grouped_parents.append((None, without_milestone))
        else:
            # Generic Issue can have any parent (excluding self and descendants)
            valid_parents = (
                BaseIssue.objects.for_project(self.project)
                .exclude(pk=issue.pk)
                .exclude(pk__in=issue.get_descendants().values_list("pk", flat=True))
                .select_related("project", "project__workspace")
                .ordered_by_key()
            )

        move_url = reverse(
            "issues:issue_move",
            kwargs={
                "workspace_slug": self.workspace.slug,
                "project_key": self.project.key,
                "key": issue.key,
            },
        )

        context = {
            "issue": issue,
            "valid_parents": valid_parents,
            "grouped_parents": grouped_parents,
            "workspace": self.workspace,
            "project": self.project,
            "move_url": move_url,
        }
        return render(request, "issues/includes/issue_move_modal_content.html", context)

    def post(self, request, *args, **kwargs):
        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])
        new_parent_key = request.POST.get("parent_key", "").strip()

        if new_parent_key:
            new_parent = get_object_or_404(BaseIssue.objects.for_project(self.project), key=new_parent_key)

            # Validate the move based on issue type rules (check against NEW parent)
            try:
                if isinstance(issue, Epic):
                    # Epics cannot have any parent
                    raise ValidationError(_("Epics cannot have a parent issue."))
                elif isinstance(issue, (Story, Bug, Chore)) and not isinstance(new_parent, Epic):
                    raise ValidationError(_("This issue can only be a child of an Epic."))
                # Generic Issue can have any parent - no validation needed
            except ValidationError as e:
                if request.htmx:
                    messages.error(request, str(e.message))
                    return render(request, "includes/messages.html")
                return JsonResponse({"error": str(e.message)}, status=400)

            # Move issue under new parent
            issue.move(new_parent, pos="last-child")
            messages.success(
                request,
                _("%(issue)s moved under %(parent)s.") % {"issue": issue.key, "parent": new_parent.key},
            )
        else:
            # Move to root (within the same project)
            # Only move if the issue is not already a root node
            if not issue.is_root():
                any_root = BaseIssue.get_first_root_node()
                if any_root:
                    # Use 'last-sibling' to append as the last root node without path shuffling
                    issue.move(any_root, pos="last-sibling")
                messages.success(request, _("%(issue)s moved to root level.") % {"issue": issue.key})
            else:
                messages.info(
                    request,
                    _("%(issue)s is already at root level.") % {"issue": issue.key},
                )

        if request.htmx:
            return HttpResponseClientRefresh()
        return JsonResponse({"success": True})


class IssueMoveToProjectView(LoginAndWorkspaceRequiredMixin, IssueViewMixin, View):
    """Move a root-level issue or milestone to another project in the same workspace."""

    def get(self, request, *args, **kwargs):
        """Return the modal content with project options."""
        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])

        # Only root-level items can be moved
        if issue.depth != 1:
            messages.error(request, _("Only root-level items can be moved to another project."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(issue.get_absolute_url())

        # Get other projects in this workspace
        target_projects = Project.objects.for_workspace(self.workspace).exclude(pk=self.project.pk).for_choices()

        context = {
            "issue": issue,
            "target_projects": target_projects,
            "workspace": self.workspace,
            "project": self.project,
        }
        return render(request, "issues/includes/issue_move_to_project_modal_content.html", context)

    def post(self, request, *args, **kwargs):
        """Perform the move to another project."""
        issue = get_object_or_404(BaseIssue.objects.for_project(self.project), key=kwargs["key"])

        target_project_id = request.POST.get("project")
        if not target_project_id:
            messages.error(request, _("Please select a target project."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(issue.get_absolute_url())

        try:
            target_project = Project.objects.get(workspace=self.workspace, pk=target_project_id)
        except Project.DoesNotExist:
            messages.error(request, _("Target project not found."))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(issue.get_absolute_url())

        try:
            issue.move_to_project(target_project)
            messages.success(
                request,
                _("%(issue)s moved to %(project)s.") % {"issue": issue.key, "project": target_project.name},
            )
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, "message") else e))
            if request.htmx:
                return render(request, "includes/messages.html")
            return redirect(issue.get_absolute_url())

        # After move, the URL changes (different project_key)
        if request.htmx:
            return HttpResponseClientRedirect(issue.get_absolute_url())

        return redirect(issue.get_absolute_url())
