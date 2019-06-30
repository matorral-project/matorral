from django.forms import ModelForm, Select, Form, ChoiceField

from .models import Epic, Story


custom_select = Select(attrs={
    'form': 'object-list',
    'onchange': 'document.querySelector("#object-list").submit();'
})


class EpicFilterForm(ModelForm):
    class Meta:
        model = Epic
        fields = ('state', 'owner')
        widgets = {
            'state': custom_select,
            'owner': custom_select,
        }


class StoryFilterForm(ModelForm):
    class Meta:
        model = Story
        fields = ('state', 'assignee')
        widgets = {
            'state': custom_select,
            'assignee': custom_select,
        }


class EpicGroupByForm(Form):
    CHOICES = [
        ('', 'None'),
        ('requester', 'Requester'),
        ('assignee', 'Assignee'),
        ('state', 'State'),
        ('sprint', 'Sprint'),
    ]

    group_by = ChoiceField(choices=CHOICES, required=False, widget=Select(attrs={'onchange': 'this.form.submit();'}))
