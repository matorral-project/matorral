from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.issues.models import (
    BaseIssue,
    Bug,
    BugSeverity,
    Chore,
    Epic,
    IssuePriority,
    IssueStatus,
    Milestone,
    Story,
    Subtask,
    SubtaskStatus,
)
from apps.issues.widgets import UserComboboxWidget
from apps.projects.models import Project
from apps.workspaces.models import Workspace

User = get_user_model()


class BaseIssueForm(forms.ModelForm):
    """Base form for all issue types."""

    parent = forms.ModelChoiceField(
        queryset=BaseIssue.objects.none(),
        required=False,
        label=_("Parent"),
        help_text=_("Select a parent issue for this item."),
    )

    class Meta:
        model = BaseIssue
        fields = ["project", "title", "description", "status", "due_date", "parent"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, project: Project | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self._setup_project_queryset()
        if project:
            self._setup_parent_queryset()

    def _setup_project_queryset(self):
        """Set up project field queryset to show projects in the same workspace."""
        if self.project:
            self.fields["project"].queryset = Project.objects.for_workspace(self.project.workspace).for_choices()
        elif self.instance and self.instance.pk and self.instance.project:
            self.fields["project"].queryset = Project.objects.filter(pk=self.instance.project_id).for_choices()

    def _setup_parent_queryset(self):
        """Override in subclasses to set appropriate parent queryset."""
        self.fields["parent"].queryset = BaseIssue.objects.for_project(self.project).for_choices()

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


class MilestoneForm(forms.ModelForm):
    """Form for creating/editing project-scoped Milestones."""

    class Meta:
        model = Milestone
        fields = ["title", "description", "status", "due_date", "priority", "owner"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "owner": UserComboboxWidget(),
        }

    def __init__(self, *args, project: Project | None = None, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project

        # Set up owner queryset - use cached workspace_members if provided
        if workspace_members is not None:
            self.fields["owner"].queryset = workspace_members
        elif self.project:
            self.fields["owner"].queryset = User.objects.for_workspace(self.project.workspace).for_choices()

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


class EpicForm(BaseIssueForm):
    """Form for creating/editing Epics."""

    milestone = forms.ModelChoiceField(
        queryset=Milestone.objects.none(),
        required=False,
        label=_("Milestone"),
        help_text=_("Optionally link this epic to a project-level milestone."),
    )

    class Meta:
        model = Epic
        fields = [
            "project",
            "title",
            "description",
            "status",
            "due_date",
            "priority",
            "assignee",
            "milestone",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "assignee": UserComboboxWidget(),
        }

    def __init__(self, *args, workspace: Workspace | None = None, workspace_members=None, **kwargs):
        self.workspace = workspace
        self.workspace_members = workspace_members
        super().__init__(*args, **kwargs)
        # Epics don't have tree parents
        if "parent" in self.fields:
            del self.fields["parent"]
        # Set up milestone queryset - milestones are project-scoped
        if self.project:
            self.fields["milestone"].queryset = Milestone.objects.for_project(self.project).for_choices()
        elif self.workspace:
            # Workspace-level epic creation - no project context yet, so no milestones available
            # Milestone selection should happen after project is selected (handled in UI)
            self.fields["project"].queryset = Project.objects.for_workspace(self.workspace).for_choices()

        # Set up assignee queryset - use cached workspace_members if provided
        if self.workspace_members is not None:
            self.fields["assignee"].queryset = self.workspace_members
        elif self.project:
            self.fields["assignee"].queryset = User.objects.for_workspace(self.project.workspace).for_choices()
        elif self.workspace:
            self.fields["assignee"].queryset = User.objects.for_workspace(self.workspace).for_choices()

    def _setup_parent_queryset(self):
        """Epics don't have tree parents - milestone is a separate FK."""
        pass


class WorkItemFormMixin:
    """Mixin for work item forms (adds priority, assignee, estimated_points)."""

    def __init__(self, *args, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Set up assignee queryset - use cached workspace_members if provided
        if workspace_members is not None:
            self.fields["assignee"].queryset = workspace_members
        elif self.project:
            self.fields["assignee"].queryset = User.objects.for_workspace(self.project.workspace).for_choices()


class StoryForm(WorkItemFormMixin, BaseIssueForm):
    """Form for creating/editing Stories."""

    class Meta:
        model = Story
        fields = [
            "project",
            "title",
            "description",
            "status",
            "due_date",
            "parent",
            "priority",
            "assignee",
            "estimated_points",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "assignee": UserComboboxWidget(),
        }

    def _setup_parent_queryset(self):
        """Stories can optionally have an Epic parent."""
        if self.project:
            self.fields["parent"].queryset = Epic.objects.for_project(self.project).for_choices()
            self.fields["parent"].label = _("Epic")
            self.fields["parent"].help_text = _("Optionally assign this story to an epic.")


class ChoreForm(WorkItemFormMixin, BaseIssueForm):
    """Form for creating/editing Chores."""

    class Meta:
        model = Chore
        fields = [
            "project",
            "title",
            "description",
            "status",
            "due_date",
            "parent",
            "priority",
            "assignee",
            "estimated_points",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "assignee": UserComboboxWidget(),
        }

    def _setup_parent_queryset(self):
        """Chores can optionally have an Epic parent."""
        if self.project:
            self.fields["parent"].queryset = Epic.objects.for_project(self.project).for_choices()
            self.fields["parent"].label = _("Epic")
            self.fields["parent"].help_text = _("Optionally assign this chore to an epic.")


class BugForm(WorkItemFormMixin, BaseIssueForm):
    """Form for creating/editing Bugs."""

    class Meta:
        model = Bug
        fields = [
            "project",
            "title",
            "description",
            "status",
            "due_date",
            "parent",
            "priority",
            "severity",
            "assignee",
            "estimated_points",
        ]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "assignee": UserComboboxWidget(),
        }

    def _setup_parent_queryset(self):
        """Bugs can optionally have an Epic parent."""
        if self.project:
            self.fields["parent"].queryset = Epic.objects.for_project(self.project).for_choices()
            self.fields["parent"].label = _("Epic")
            self.fields["parent"].help_text = _("Optionally assign this bug to an epic.")


# Form registry for type-specific forms (milestones are workspace-scoped, not issue types)
ISSUE_FORM_CLASSES = {
    "epic": EpicForm,
    "story": StoryForm,
    "bug": BugForm,
    "chore": ChoreForm,
}

ISSUE_TYPES = list(ISSUE_FORM_CLASSES.keys())


def get_form_class_for_type(issue_type: str) -> type[BaseIssueForm]:
    """Get the form class for a given issue type."""
    return ISSUE_FORM_CLASSES.get(issue_type, ChoreForm)


class BulkActionForm(forms.Form):
    """Base form for bulk operations on issues."""

    issues = forms.ModelMultipleChoiceField(
        queryset=BaseIssue.objects.none(),
        required=False,
        to_field_name="key",  # Validate by key instead of pk
        error_messages={"required": _("No issues selected.")},
    )
    page = forms.IntegerField(min_value=1, initial=1, required=False)
    search = forms.CharField(required=False)
    status_filter = forms.CharField(required=False)
    type_filter = forms.CharField(required=False)
    assignee_filter = forms.CharField(required=False)
    group_by = forms.CharField(required=False)

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if queryset is not None:
            self.fields["issues"].queryset = queryset

    def clean_page(self):
        return self.cleaned_data.get("page") or 1

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()

    def clean_status_filter(self):
        return (self.cleaned_data.get("status_filter") or "").strip()

    def clean_type_filter(self):
        return (self.cleaned_data.get("type_filter") or "").strip()

    def clean_assignee_filter(self):
        return (self.cleaned_data.get("assignee_filter") or "").strip()

    def clean_group_by(self):
        return (self.cleaned_data.get("group_by") or "").strip()


class WorkspaceBulkActionForm(BulkActionForm):
    """Base form for workspace-level bulk operations on issues."""

    # Accept 'epics' as an alias for 'issues' (for project_epics embed)
    epics = forms.ModelMultipleChoiceField(
        queryset=BaseIssue.objects.none(),
        required=False,
        to_field_name="key",
    )
    project_filter = forms.CharField(required=False)
    sprint_filter = forms.CharField(required=False)
    epic_filter = forms.CharField(required=False)
    milestone_filter = forms.CharField(required=False)
    priority_filter = forms.CharField(required=False)

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, queryset=queryset, **kwargs)
        if queryset is not None:
            self.fields["epics"].queryset = queryset

    def clean(self):
        cleaned_data = super().clean()
        # Merge 'epics' into 'issues' if provided
        epics = cleaned_data.get("epics")
        issues = cleaned_data.get("issues")
        if epics and not issues:
            cleaned_data["issues"] = epics
        return cleaned_data

    def clean_project_filter(self):
        return (self.cleaned_data.get("project_filter") or "").strip()

    def clean_sprint_filter(self):
        return (self.cleaned_data.get("sprint_filter") or "").strip()

    def clean_epic_filter(self):
        return (self.cleaned_data.get("epic_filter") or "").strip()

    def clean_milestone_filter(self):
        return (self.cleaned_data.get("milestone_filter") or "").strip()

    def clean_priority_filter(self):
        return (self.cleaned_data.get("priority_filter") or "").strip()


class WorkspaceBulkAssigneeForm(WorkspaceBulkActionForm):
    """Form for workspace-level bulk updating issue assignees."""

    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label=None,
    )

    def __init__(self, *args, workspace: Workspace, queryset=None, workspace_members=None, **kwargs):
        super().__init__(*args, queryset=queryset, **kwargs)
        if workspace_members is not None:
            self.fields["assignee"].queryset = workspace_members
        else:
            self.fields["assignee"].queryset = User.objects.for_workspace(workspace).for_choices()

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("issues"):
            raise forms.ValidationError(_("No issues selected."))
        return cleaned_data


# ============================================================================
# Issue inline edit form
# ============================================================================


class IssueRowInlineEditForm(forms.Form):
    """Form for inline editing issue rows in list views."""

    title = forms.CharField(
        max_length=255,
        required=True,
        error_messages={"required": _("Title is required.")},
    )
    status = forms.ChoiceField(
        choices=IssueStatus.choices,
        required=True,
    )
    priority = forms.ChoiceField(
        choices=IssuePriority.choices,
        required=False,
    )
    assignee = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
    )
    estimated_points = forms.IntegerField(
        min_value=0,
        required=False,
    )

    def __init__(self, *args, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace_members is not None:
            self.fields["assignee"].queryset = workspace_members

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


class EpicDetailInlineEditForm(IssueRowInlineEditForm):
    """Form for inline editing epic details page. Extends row form with description, due_date, milestone."""

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    milestone = forms.ModelChoiceField(
        queryset=None,
        required=False,
    )

    def __init__(self, *args, workspace_members=None, milestones=None, **kwargs):
        super().__init__(*args, workspace_members=workspace_members, **kwargs)
        if milestones is not None:
            self.fields["milestone"].queryset = milestones

    def clean_description(self):
        description = self.cleaned_data.get("description")
        if description:
            description = description.strip()
        return description


class IssueDetailInlineEditForm(IssueRowInlineEditForm):
    """Form for inline editing non-epic issue details page.

    Extends row form with description, due_date, parent, severity.
    """

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    parent = forms.ModelChoiceField(
        queryset=None,
        required=False,
    )
    severity = forms.ChoiceField(
        choices=BugSeverity.choices,
        required=False,
    )

    def __init__(self, *args, workspace_members=None, epics=None, **kwargs):
        super().__init__(*args, workspace_members=workspace_members, **kwargs)
        if epics is not None:
            self.fields["parent"].queryset = epics

    def clean_description(self):
        description = self.cleaned_data.get("description")
        if description:
            description = description.strip()
        return description


# ============================================================================
# Milestone inline edit form
# ============================================================================


class MilestoneRowInlineEditForm(forms.Form):
    """Form for inline editing milestone rows in list views."""

    title = forms.CharField(
        max_length=255,
        required=True,
        error_messages={"required": _("Title is required.")},
    )
    status = forms.ChoiceField(
        choices=IssueStatus.choices,
        required=True,
    )
    priority = forms.ChoiceField(
        choices=IssuePriority.choices,
        required=False,
    )
    owner = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace_members is not None:
            self.fields["owner"].queryset = workspace_members

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


class MilestoneDetailInlineEditForm(MilestoneRowInlineEditForm):
    """Form for inline editing milestone details page. Extends row form with description."""

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_description(self):
        description = self.cleaned_data.get("description")
        if description:
            description = description.strip()
        return description


# ============================================================================
# Subtask forms
# ============================================================================


class SubtaskForm(forms.ModelForm):
    """Form for creating a new subtask."""

    class Meta:
        model = Subtask
        fields = ["title"]

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


class SubtaskInlineEditForm(forms.Form):
    """Form for inline editing subtask title and status."""

    title = forms.CharField(
        max_length=255,
        required=True,
        error_messages={"required": _("Title is required.")},
    )
    status = forms.ChoiceField(
        choices=SubtaskStatus.choices,
        required=True,
    )

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if title:
            title = title.strip()
        return title


# ============================================================================
# Issue type conversion form
# ============================================================================


# Type choices for conversion (excludes Epic)
CONVERTIBLE_TYPE_CHOICES = [
    ("story", _("Story")),
    ("bug", _("Bug")),
    ("chore", _("Chore")),
]


class IssueConvertTypeForm(forms.Form):
    """Form for converting an issue to a different type."""

    target_type = forms.ChoiceField(
        choices=[],  # Set dynamically in __init__
        required=True,
        label=_("Convert to"),
    )
    severity = forms.ChoiceField(
        choices=BugSeverity.choices,
        required=False,
        initial=BugSeverity.MINOR,
        label=_("Severity"),
        help_text=_("Required when converting to Bug."),
    )

    def __init__(self, *args, current_type: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter out the current type from choices
        self.current_type = current_type
        if current_type:
            self.fields["target_type"].choices = [
                (value, label) for value, label in CONVERTIBLE_TYPE_CHOICES if value != current_type
            ]
        else:
            self.fields["target_type"].choices = CONVERTIBLE_TYPE_CHOICES

    def clean(self):
        cleaned_data = super().clean()
        target_type = cleaned_data.get("target_type")
        severity = cleaned_data.get("severity")

        # Severity is required when converting to Bug
        if target_type == "bug" and not severity:
            cleaned_data["severity"] = BugSeverity.MINOR

        return cleaned_data


class IssuePromoteToEpicForm(forms.Form):
    """Form for promoting a work item to an Epic."""

    milestone = forms.ModelChoiceField(
        queryset=Milestone.objects.none(),
        required=False,
        label=_("Milestone"),
        help_text=_("Optionally link the new Epic to a milestone."),
    )
    convert_subtasks = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Convert subtasks to Stories"),
        help_text=_("If checked, subtasks will become Stories under the new Epic. Otherwise they will be deleted."),
    )

    def __init__(self, *args, project: Project | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields["milestone"].queryset = Milestone.objects.for_project(project).for_choices()
