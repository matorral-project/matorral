from django.forms import Form, ChoiceField, Select


class SprintGroupByForm(Form):
    CHOICES = [
        ("", "None"),
        ("requester", "Requester"),
        ("assignee", "Assignee"),
        ("state", "State"),
        ("epic", "Epic"),
    ]

    group_by = ChoiceField(
        choices=CHOICES,
        required=False,
        widget=Select(
            attrs={
                "onchange": 'Turbolinks.visit(document.location.pathname + "?group_by=" + this.value); return false;'
            }
        ),
    )
