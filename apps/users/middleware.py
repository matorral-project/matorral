import zoneinfo

from django.utils import timezone


class UserTimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if user.timezone:
                timezone.activate(zoneinfo.ZoneInfo(user.timezone))
            else:
                timezone.deactivate()
        return self.get_response(request)
