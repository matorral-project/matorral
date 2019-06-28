from urllib.parse import quote_plus, unquote_plus

from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject


def site(request):
    return dict(
        current_site=SimpleLazyObject(lambda: get_current_site(request)),
    )


def navigation(request):
    return dict(
        encoded_url=quote_plus(request.get_full_path()),
        next_url=unquote_plus(request.GET.get('next', ''))
    )
