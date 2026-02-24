from django.contrib.sites.models import Site
from django.utils.html import escape


class HtmxPageTitleMiddleware:
    """Inject a <title> tag into HTMX fragment responses for automatic browser tab updates.

    HTMX 2.x automatically updates document.title when it finds a <title> tag
    in the response content. This middleware adds one for HTMX requests that
    have page_title in their template context.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_template_response(self, request, response):
        if not getattr(request, "htmx", False) or not request.htmx:
            return response

        context_data = getattr(response, "context_data", None)
        if context_data is None:
            return response

        page_title = context_data.get("page_title", "")
        if not page_title:
            return response

        site_name = Site.objects.get_current().name
        full_title = f"{page_title} | {site_name}"

        def inject_title(response):
            title_tag = f"<title>{escape(full_title)}</title>"
            response.content = title_tag.encode() + response.content

        response.add_post_render_callback(inject_title)
        return response
