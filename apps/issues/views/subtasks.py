from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from apps.issues.cascade import build_cascade_oob_response
from apps.issues.forms import SubtaskForm, SubtaskInlineEditForm
from apps.issues.models import Subtask, SubtaskStatus
from apps.issues.utils import get_cached_content_type
from apps.issues.views.comments import IssueCommentsViewMixin
from apps.workspaces.mixins import LoginAndWorkspaceRequiredMixin

# Maximum number of subtasks allowed per parent
MAX_SUBTASKS_PER_PARENT = 20


class SubtaskViewMixin(IssueCommentsViewMixin):
    """Base mixin for subtask views. Extends IssueCommentsViewMixin for workspace/project/issue setup."""

    def get_subtasks(self):
        """Get all subtasks for the current issue."""
        return Subtask.objects.for_parent(self.issue)

    def get_subtask_count(self):
        """Get the count of subtasks for the current issue."""
        return self.get_subtasks().count()

    def can_add_subtask(self):
        """Check if more subtasks can be added (under the limit)."""
        return self.get_subtask_count() < MAX_SUBTASKS_PER_PARENT

    def get_subtasks_context(self):
        """Get common context for subtask templates."""
        subtasks = self.get_subtasks()
        subtask_count = subtasks.count()
        return {
            "workspace": self.workspace,
            "project": self.project,
            "issue": self.issue,
            "subtasks": subtasks,
            "subtask_count": subtask_count,
            "can_add_subtask": subtask_count < MAX_SUBTASKS_PER_PARENT,
            "max_subtasks": MAX_SUBTASKS_PER_PARENT,
            "status_choices": SubtaskStatus.choices,
        }


class SubtaskListView(LoginAndWorkspaceRequiredMixin, SubtaskViewMixin, View):
    """GET subtasks list for an issue via HTMX."""

    def get(self, request, *args, **kwargs):
        context = self.get_subtasks_context()
        return render(request, "issues/includes/subtasks_list.html", context)


class SubtaskCreateView(LoginAndWorkspaceRequiredMixin, SubtaskViewMixin, View):
    """POST to create a new subtask and return updated list."""

    def post(self, request, *args, **kwargs):
        if not self.can_add_subtask():
            return HttpResponseBadRequest(
                _("Maximum number of subtasks reached (%(max)s).") % {"max": MAX_SUBTASKS_PER_PARENT}
            )

        form = SubtaskForm(request.POST)
        if form.is_valid():
            subtask = form.save(commit=False)
            content_type = get_cached_content_type(type(self.issue))
            subtask.content_type = content_type
            subtask.object_id = self.issue.pk

            # Set position to be at the end
            existing_count = self.get_subtask_count()
            subtask.position = existing_count
            subtask.save()

        context = self.get_subtasks_context()
        return render(request, "issues/includes/subtasks_list.html", context)


class SubtaskInlineEditView(LoginAndWorkspaceRequiredMixin, SubtaskViewMixin, View):
    """GET to show edit form, POST to save changes."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.subtask = get_object_or_404(
            Subtask.objects.for_parent(self.issue),
            pk=kwargs["subtask_pk"],
        )

    def get(self, request, *args, **kwargs):
        # Check if this is a cancel request (returning to display mode)
        if request.GET.get("cancel"):
            context = {
                "workspace": self.workspace,
                "project": self.project,
                "issue": self.issue,
                "subtask": self.subtask,
                "status_choices": SubtaskStatus.choices,
            }
            return render(request, "issues/includes/subtask_row.html", context)

        # Show edit form
        context = {
            "workspace": self.workspace,
            "project": self.project,
            "issue": self.issue,
            "subtask": self.subtask,
            "status_choices": SubtaskStatus.choices,
        }
        return render(request, "issues/includes/subtask_row_edit.html", context)

    def post(self, request, *args, **kwargs):
        form = SubtaskInlineEditForm(request.POST)
        if form.is_valid():
            old_status = self.subtask.status
            self.subtask.title = form.cleaned_data["title"]
            self.subtask.status = form.cleaned_data["status"]
            self.subtask.save()

            context = {
                "workspace": self.workspace,
                "project": self.project,
                "issue": self.issue,
                "subtask": self.subtask,
                "status_choices": SubtaskStatus.choices,
            }
            response = render(request, "issues/includes/subtask_row.html", context)

            # Check cascade opportunities if status changed
            new_status = form.cleaned_data["status"]
            if old_status != new_status:
                response = build_cascade_oob_response(request, self.subtask, new_status, response)

            return response

        context = {
            "workspace": self.workspace,
            "project": self.project,
            "issue": self.issue,
            "subtask": self.subtask,
            "status_choices": SubtaskStatus.choices,
        }
        return render(request, "issues/includes/subtask_row.html", context)


class SubtaskDeleteView(LoginAndWorkspaceRequiredMixin, SubtaskViewMixin, View):
    """POST to delete a subtask and return updated list."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.subtask = get_object_or_404(
            Subtask.objects.for_parent(self.issue),
            pk=kwargs["subtask_pk"],
        )

    def post(self, request, *args, **kwargs):
        self.subtask.delete()

        context = self.get_subtasks_context()
        return render(request, "issues/includes/subtasks_list.html", context)


class SubtaskStatusToggleView(LoginAndWorkspaceRequiredMixin, SubtaskViewMixin, View):
    """POST to cycle subtask status: TODO -> IN_PROGRESS -> DONE -> TODO."""

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.subtask = get_object_or_404(
            Subtask.objects.for_parent(self.issue),
            pk=kwargs["subtask_pk"],
        )

    def post(self, request, *args, **kwargs):
        # Cycle through statuses: TODO -> IN_PROGRESS -> DONE -> TODO
        if self.subtask.status == SubtaskStatus.TODO:
            self.subtask.status = SubtaskStatus.IN_PROGRESS
        elif self.subtask.status == SubtaskStatus.IN_PROGRESS:
            self.subtask.status = SubtaskStatus.DONE
        elif self.subtask.status == SubtaskStatus.DONE:
            self.subtask.status = SubtaskStatus.TODO
        else:
            # WONT_DO -> TODO
            self.subtask.status = SubtaskStatus.TODO
        self.subtask.save()

        context = {
            "workspace": self.workspace,
            "project": self.project,
            "issue": self.issue,
            "subtask": self.subtask,
            "status_choices": SubtaskStatus.choices,
        }
        return render(request, "issues/includes/subtask_row.html", context)
