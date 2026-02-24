from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.issues.models import BaseIssue
from apps.sprints.models import Sprint, SprintStatus
from apps.ui.widgets import UserComboboxWidget
from apps.workspaces.models import Workspace

User = get_user_model()


class SprintForm(forms.ModelForm):
    """Form for creating/editing Sprints."""

    class Meta:
        model = Sprint
        fields = [
            "name",
            "goal",
            "status",
            "start_date",
            "end_date",
            "capacity",
            "owner",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "goal": forms.Textarea(attrs={"rows": 3}),
            "owner": UserComboboxWidget(),
        }

    def __init__(self, *args, workspace: Workspace | None = None, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace

        # Set up owner queryset - use cached workspace_members if provided
        if workspace_members is not None:
            self.fields["owner"].queryset = workspace_members
        elif self.workspace:
            self.fields["owner"].queryset = User.objects.for_workspace(self.workspace).for_choices()

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name:
            name = name.strip()
        return name


class SprintBulkActionForm(forms.Form):
    """Base form for bulk operations on sprints."""

    sprints = forms.ModelMultipleChoiceField(
        queryset=Sprint.objects.none(),
        required=False,
        to_field_name="key",
    )
    page = forms.IntegerField(required=False, initial=1)
    search = forms.CharField(required=False)
    status_filter = forms.CharField(required=False)
    owner_filter = forms.CharField(required=False)

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            self.fields["sprints"].queryset = Sprint.objects.for_workspace(workspace).for_choices()

    def clean_page(self):
        return self.cleaned_data.get("page") or 1

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()

    def clean_status_filter(self):
        return (self.cleaned_data.get("status_filter") or "").strip()

    def clean_owner_filter(self):
        return (self.cleaned_data.get("owner_filter") or "").strip()


class SprintBulkOwnerForm(SprintBulkActionForm):
    """Form for bulk owner assignment on sprints."""

    owner = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label=None,
    )

    def __init__(self, *args, workspace: Workspace | None = None, workspace_members=None, **kwargs):
        super().__init__(*args, workspace=workspace, **kwargs)
        # Set up owner queryset - use cached workspace_members if provided
        if workspace_members is not None:
            self.fields["owner"].queryset = workspace_members
        elif workspace:
            self.fields["owner"].queryset = User.objects.for_workspace(workspace).for_choices()


class AddIssuesToSprintForm(forms.Form):
    """Form for adding issues to a sprint."""

    issues = forms.ModelMultipleChoiceField(
        queryset=BaseIssue.objects.none(),
        required=True,
        to_field_name="key",
        error_messages={"required": _("Please select at least one issue.")},
    )

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            # Show work items in the workspace that are not assigned to any sprint
            self.fields["issues"].queryset = (
                BaseIssue.objects.for_workspace(workspace)
                .work_items()
                .filter(story__sprint__isnull=True)
                .filter(bug__sprint__isnull=True)
                .filter(chore__sprint__isnull=True)
                .filter(issue__sprint__isnull=True)
            )


class IssueAddToSprintForm(forms.Form):
    """Form for adding a single issue to a sprint."""

    sprint = forms.ModelChoiceField(
        queryset=Sprint.objects.none(),
        required=True,
        empty_label=None,
        error_messages={"required": _("Please select a sprint.")},
    )

    def __init__(self, *args, workspace: Workspace | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace:
            # Show sprints in planning or active status
            self.fields["sprint"].queryset = (
                Sprint.objects.for_workspace(workspace).not_archived().order_by("-status", "-start_date")
            )


# ============================================================================
# Sprint inline edit form
# ============================================================================


class SprintRowInlineEditForm(forms.Form):
    """Form for inline editing sprint rows in list views."""

    name = forms.CharField(
        max_length=255,
        required=True,
        error_messages={"required": _("Name is required.")},
    )
    status = forms.ChoiceField(
        choices=SprintStatus.choices,
        required=True,
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    owner = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
    )
    capacity = forms.IntegerField(
        min_value=0,
        required=False,
    )

    def __init__(self, *args, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace_members is not None:
            self.fields["owner"].queryset = workspace_members

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name:
            name = name.strip()
        return name


class SprintDetailInlineEditForm(SprintRowInlineEditForm):
    """Form for inline editing sprint details page. Extends row form with goal."""

    goal = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_goal(self):
        goal = self.cleaned_data.get("goal")
        if goal:
            goal = goal.strip()
        return goal
