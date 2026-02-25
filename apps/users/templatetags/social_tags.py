from django import template
from django.contrib.sites.shortcuts import get_current_site

from allauth.socialaccount.models import SocialApp

register = template.Library()


@register.simple_tag(takes_context=True)
def social_apps(context):
    """
    Returns a list of social authentication provider objects.

    Usage: `{% social_apps as social_app_list %}`.

    Then within the template context, `social_app_list` will hold
    a list of social app providers configured for the current site.
    """

    request = context["request"]
    current_site = get_current_site(request)
    apps = SocialApp.objects.filter(sites=current_site)
    providers = []
    for app in apps:
        provider = app.get_provider(request)
        provider.logo_path = f"images/socialauth/{provider.id}-logo.svg"
        providers.append(provider)
    return providers
