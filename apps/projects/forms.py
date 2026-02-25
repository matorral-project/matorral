import re

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.issues.widgets import UserComboboxWidget
from apps.projects.models import Project, ProjectStatus
from apps.workspaces.models import Workspace

User = get_user_model()


class BulkActionForm(forms.Form):
    """Base form for bulk operations on projects."""

    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),
        required=False,
        to_field_name="key",  # Validate by key instead of pk
        error_messages={"required": _("No projects selected.")},
    )
    page = forms.IntegerField(min_value=1, initial=1, required=False)
    search = forms.CharField(required=False)
    status_filter = forms.CharField(required=False)
    lead_filter = forms.CharField(required=False)
    group_by = forms.CharField(required=False)

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if queryset is not None:
            self.fields["projects"].queryset = queryset

    def clean_page(self):
        return self.cleaned_data.get("page") or 1

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()

    def clean_status_filter(self):
        return (self.cleaned_data.get("status_filter") or "").strip()

    def clean_lead_filter(self):
        return (self.cleaned_data.get("lead_filter") or "").strip()

    def clean_group_by(self):
        return (self.cleaned_data.get("group_by") or "").strip()


class BulkLeadForm(BulkActionForm):
    """Form for bulk updating project leads."""

    lead = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label=None,
    )

    def __init__(self, *args, workspace: Workspace, queryset=None, workspace_members=None, **kwargs):
        super().__init__(*args, queryset=queryset, **kwargs)
        if workspace_members is not None:
            self.fields["lead"].queryset = workspace_members
        else:
            self.fields["lead"].queryset = User.objects.for_workspace(workspace).for_choices()
        self.fields["projects"].required = True


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "key", "description", "status", "lead"]
        widgets = {
            "lead": UserComboboxWidget(),
        }

    def __init__(self, *args, workspace=None, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace = workspace
        if workspace_members is not None:
            self.fields["lead"].queryset = workspace_members
        elif workspace:
            self.fields["lead"].queryset = User.objects.for_workspace(workspace).for_choices()
        elif self.instance and self.instance.pk:
            self.fields["lead"].queryset = User.objects.for_workspace(self.instance.workspace).for_choices()

    def clean_key(self):
        key = self.cleaned_data.get("key")
        if not key:
            return key

        # Validate key format: only ASCII letters (A-Z), max 6 characters
        if not re.match(r"^[A-Za-z]+$", key):
            raise forms.ValidationError(_("Key must contain only letters (A-Z)."))

        if len(key) > 6:
            raise forms.ValidationError(_("Key must be at most 6 characters."))

        workspace = self.workspace or (self.instance.workspace if self.instance and self.instance.pk else None)
        if not workspace:
            return key

        qs = Project.objects.for_workspace(workspace).with_key(key, exclude=self.instance)
        if qs.exists():
            raise forms.ValidationError(_("A project with this key already exists in this workspace."))
        return key


# ============================================================================
# Project inline edit form
# ============================================================================


class ProjectRowInlineEditForm(forms.Form):
    """Form for inline editing project rows in list views."""

    name = forms.CharField(
        max_length=100,
        required=True,
        error_messages={"required": _("Name is required.")},
    )
    status = forms.ChoiceField(
        choices=ProjectStatus.choices,
        required=True,
    )
    lead = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
    )

    def __init__(self, *args, workspace_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        if workspace_members is not None:
            self.fields["lead"].queryset = workspace_members

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name:
            name = name.strip()
        return name


class ProjectDetailInlineEditForm(ProjectRowInlineEditForm):
    """Form for inline editing project details page. Extends row form with description."""

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_description(self):
        description = self.cleaned_data.get("description")
        if description:
            description = description.strip()
        return description
