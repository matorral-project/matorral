from django.views import defaults


def bad_request(request, exception):
    return defaults.bad_request(request, exception, template_name="errors/400.html")


def permission_denied(request, exception):
    return defaults.permission_denied(request, exception, template_name="errors/403.html")


def page_not_found(request, exception):
    return defaults.page_not_found(request, exception, template_name="errors/404.html")


def server_error(request):
    return defaults.server_error(request, template_name="errors/500.html")


def too_many_requests(request, exception):
    return defaults.bad_request(request, exception, template_name="errors/429.html")
