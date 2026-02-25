import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# --- Templates ---

_FIELD_WRAPPER_START = """<div class="w-full mt-2" {% include "django/forms/attrs.html" %}>"""
_FIELD_WRAPPER_END = """
  <small class="mt-text-muted">{{ form_field.help_text|safe }}</small>
  {{ form_field.errors }}
</div>"""

_TEMPLATES = {
    "checkbox": _FIELD_WRAPPER_START
    + """<div>
    <label class="font-bold cursor-pointer flex items-center gap-2">
      {{ form_field }}
      {{ form_field.label }}
    </label>
  </div>"""
    + _FIELD_WRAPPER_END,
    "usercombobox": _FIELD_WRAPPER_START
    + """{% load i18n %}
  <label class="block mb-1 font-bold" for="{{ combobox_id }}">{{ form_field.label }}</label>
  {% include "includes/user_combobox.html" %}"""
    + _FIELD_WRAPPER_END,
    "_default": _FIELD_WRAPPER_START
    + """<label class="block mb-1 font-bold" for="{{ form_field.id_for_label }}">{{ form_field.label }}</label>
  {{ form_field }}"""
    + _FIELD_WRAPPER_END,
}

_HIDDEN_TEMPLATE = template.Template("{{ form_field }}")


# --- Tags ---


@register.simple_tag
def json_vals(**kwargs):
    """Serialize kwargs to JSON for use in hx-vals attributes.

    Usage: {% json_vals status=status_filter type=type_filter as my_vals %}
    """
    return mark_safe(json.dumps({k: str(v) if v else "" for k, v in kwargs.items()}))


def _transform_x_attrs(attrs):
    """Convert Python-safe kwarg keys back to Alpine.js attribute syntax.
    e.g. xbind__placeholder -> x-bind:placeholder
    Note: @click-style and dot-modifier attributes are not supported.
    """

    def _convert(key):
        return f"x-{key[1:].replace('__', ':')}" if key.startswith("x") else key

    return {_convert(k): v for k, v in attrs.items()}


@register.simple_tag(takes_context=True)
def render_form_fields(context, form):
    return mark_safe("".join(render_field(context, form[f]) for f in form.fields))


@register.simple_tag(takes_context=True)
def render_field(context, form_field, **attrs):
    if form_field.is_hidden:
        return _HIDDEN_TEMPLATE.render(template.Context({"form_field": form_field}))

    widget_type = form_field.widget_type
    ctx = {"form_field": form_field, "attrs": _transform_x_attrs(attrs)}

    if widget_type == "usercombobox":
        ctx.update(_combobox_context(form_field, context.get("request")))

    tmpl = template.Template(_TEMPLATES.get(widget_type, _TEMPLATES["_default"]))
    return mark_safe(tmpl.render(template.Context(ctx)))


# --- Helpers ---


def _combobox_context(form_field, request=None):
    choices = [(str(val), str(label)) for val, label in form_field.field.choices if val]
    selected_id = str(form_field.value() or "")
    selected_name = next((label for val, label in choices if val == selected_id), "")

    current_user_id, current_user_name = "", ""
    if request and getattr(request, "user", None) and request.user.is_authenticated:
        current_user_id = request.user.pk
        current_user_name = request.user.get_display_name()

    return {
        "combobox_name": form_field.html_name,
        "combobox_choices": choices,
        "combobox_selected_id": selected_id,
        "combobox_selected_name": selected_name,
        "combobox_id": f"id_{form_field.html_name}",
        "combobox_current_user_id": str(current_user_id),
        "combobox_current_user_name": str(current_user_name),
    }
