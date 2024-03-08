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
                "hx-get": ".",
                "hx-trigger": "change",
                "hx-target": "body",
                "hx-replace-url": "true",
            }
        ),
    )
