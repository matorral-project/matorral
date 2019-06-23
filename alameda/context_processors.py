from django.contrib.sites.shortcuts import get_current_site
from django.utils.functional import SimpleLazyObject


def site(request):
    return dict(
        current_site=SimpleLazyObject(lambda: get_current_site(request)),
    )
