from django.forms import ModelForm, Select

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
        fields = ('state', 'owner', 'assignee')
        widgets = {
            'state': custom_select,
            'owner': custom_select,
            'assignee': custom_select,
        }
