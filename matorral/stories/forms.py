from django.forms import Select, Form, ChoiceField, ModelChoiceField, ModelForm

from matorral.users.models import User

from .models import EpicState, StoryState, Epic


custom_select = Select(attrs={
    'form': 'object-list',
    'onchange': 'postForm(document.querySelector("#object-list"));'
})


class EpicFilterForm(Form):
    state = ModelChoiceField(
        empty_label='--Set State--',
        queryset=EpicState.objects.all(),
        required=False,
        widget=custom_select
    )

    owner = ModelChoiceField(
        empty_label='--Set Owner--',
        queryset=User.objects.all(),
        required=False,
        widget=custom_select
    )


class StoryFilterForm(Form):
    state = ModelChoiceField(
        empty_label='--Set State--',
        queryset=StoryState.objects.all(),
        required=False,
        widget=custom_select
    )

    assignee = ModelChoiceField(
        empty_label='--Set Assignee--',
        queryset=User.objects.all(),
        required=False,
        widget=custom_select
    )


class EpicGroupByForm(Form):
    CHOICES = [
        ('', 'None'),
        ('requester', 'Requester'),
        ('assignee', 'Assignee'),
        ('state', 'State'),
        ('sprint', 'Sprint'),
    ]

    group_by = ChoiceField(choices=CHOICES, required=False, widget=Select(attrs={'onchange': 'this.form.submit();'}))


class EpicForm(ModelForm):
    class Meta:
        model = Epic
        fields = ['title', 'description', 'owner', 'state', 'priority', 'tags']

    def __init__(self, *args, **kwargs):
        self.workspace = kwargs.pop('workspace', None)
        super(EpicForm, self).__init__(*args, **kwargs)
        self.fields['owner'].queryset = User.objects.filter(is_active=True, workspace=self.workspace)

    def save(self, commit=True):
        instance = super(EpicForm, self).save(commit=False)
        instance.workspace = self.workspace
        if commit:
            instance.save()
        return instance
