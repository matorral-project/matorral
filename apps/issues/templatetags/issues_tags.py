import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def json_vals(**kwargs):
    """Serialize kwargs to JSON for use in hx-vals attributes.

    Usage: {% json_vals status=status_filter type=type_filter as my_vals %}
    """
    return mark_safe(json.dumps({k: str(v) if v else "" for k, v in kwargs.items()}))
