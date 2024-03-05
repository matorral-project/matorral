from django import template
from django.utils.safestring import mark_safe as safe


register = template.Library()


@register.filter
def to_html(text):
    def replace_links_with_html(text):
        import re

        url_re = re.compile(r"(https?://\S+)")
        return url_re.sub(r'<a target="_blank" href="\1">\1</a>', text)

    html = replace_links_with_html(text)
    html = html.replace("\n", "<br>")
    return safe(html)
