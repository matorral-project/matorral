from django.utils.text import slugify

from .models import Workspace


def get_next_unique_workspace_slug(workspace_name: str) -> str:
    base_value = slugify(workspace_name[:40])
    return _get_next_unique_slug_value(base_value)


def _get_next_unique_slug_value(slug_value: str) -> str:
    if not Workspace.objects.filter(slug=slug_value).exists():
        return slug_value

    suffix = 2
    while True:
        next_slug = _get_next_slug(slug_value, suffix)
        if not Workspace.objects.filter(slug=next_slug).exists():
            return next_slug
        suffix += 1


def _get_next_slug(base_value: str, suffix: int, max_length: int = 100) -> str:
    suffix_length = len(str(suffix)) + 1  # + 1 for the "-" character
    if suffix_length >= max_length:
        raise ValueError(f"Suffix {suffix} is too long to create a unique slug! ")
    return f"{base_value[: max_length - suffix_length]}-{suffix}"
