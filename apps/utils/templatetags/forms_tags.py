from django import template
from django.template.loader import get_template, select_template
from django.utils.safestring import mark_safe

register = template.Library()


def _transform_x_attrs(attrs):
    """Convert Python-safe kwarg keys back to Alpine.js attribute syntax.
    e.g. xbind__placeholder -> x-bind:placeholder
    """

    def _convert(key):
        return f"x-{key[1:].replace('__', ':')}" if key.startswith("x") else key

    return {_convert(k): v for k, v in attrs.items()}


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


def _render_field(context, form_field, **attrs):
    if form_field.is_hidden:
        return mark_safe(get_template("utils/forms/field_hidden.html").render({"form_field": form_field}))

    widget_type = form_field.widget_type
    ctx = {"form_field": form_field, "attrs": _transform_x_attrs(attrs)}

    if widget_type == "usercombobox":
        ctx.update(_combobox_context(form_field, context.get("request")))

    tmpl = select_template(
        [
            f"utils/forms/field_{widget_type}.html",
            "utils/forms/field_default.html",
        ]
    )
    return mark_safe(tmpl.render(ctx))


@register.simple_tag(takes_context=True)
def render_form_fields(context, form):
    return mark_safe("".join(_render_field(context, form[f]) for f in form.fields))


@register.simple_tag(takes_context=True)
def render_field(context, form_field, **attrs):
    return _render_field(context, form_field, **attrs)
