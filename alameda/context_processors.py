from urllib.parse import quote_plus, unquote_plus

from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject

from .forms import SearchForm


def site(request):
    return dict(
        current_site=SimpleLazyObject(lambda: get_current_site(request)),
    )


def navigation(request):
    params = dict(
        encoded_url=quote_plus(request.get_full_path()),
        next_url=unquote_plus(request.GET.get('next', ''))
    )

    try:
        params['page'] = int(request.GET.get('page', 0))
    except ValueError:
        pass

    get_vars = request.GET.copy()
    try:
        get_vars.pop('page')
    except KeyError:
        pass

    params['get_vars'] = "&" + get_vars.urlencode()

    return params


def search(request):
    return dict(search_form=SearchForm(request.GET))
