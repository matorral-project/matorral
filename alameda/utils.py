from urllib.parse import unquote_plus, parse_qsl, urlencode, urlparse, urlunparse


def get_clean_next_url(request, fallback_url):
    next_url = request.GET.get('next')
    if next_url is None:
        return fallback_url

    unquoted_url = unquote_plus(next_url)
    scheme, netloc, path, params, query, fragment = urlparse(unquoted_url)
    query_dict = dict(parse_qsl(query))

    for param in ('next', 'sprint', 'epic'):
        try:
            del query_dict[param]
        except KeyError:
            pass

    return urlunparse([scheme, netloc, path, params, urlencode(query_dict), fragment])
