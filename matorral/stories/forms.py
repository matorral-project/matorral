from django.forms import Select, Form, ChoiceField, ModelChoiceField

from matorral.users.models import User

from .models import EpicState, StoryState


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
