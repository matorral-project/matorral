from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import connection

# Process-level cache with database-aware keys
_content_type_cache = {}


def get_cached_content_type(model_class):
    """Get ContentType for a model with database-aware caching to avoid deadlocks.

    Uses a process-level cache with database-aware keys to prevent concurrent
    ContentType lookups that can cause deadlocks, while ensuring cached values
    are not reused across different databases (e.g., in test environments).

    Args:
        model_class: The Django model class to get the ContentType for

    Returns:
        ContentType instance for the given model
    """
    # Include database alias in cache key to handle different database contexts
    db_alias = connection.alias
    cache_key = (db_alias, model_class._meta.app_label, model_class._meta.model_name)

    if cache_key not in _content_type_cache:
        _content_type_cache[cache_key] = ContentType.objects.get_for_model(model_class)

    return _content_type_cache[cache_key]


def get_work_item_ctype_ids():
    """Return cached ContentType IDs for work item models (Story, Bug, Chore).

    Uses get_cached_content_type() to avoid repeated DB lookups.
    """
    return [
        get_cached_content_type(apps.get_model("issues", "Story")).id,
        get_cached_content_type(apps.get_model("issues", "Bug")).id,
        get_cached_content_type(apps.get_model("issues", "Chore")).id,
    ]


def clear_content_type_cache():
    """Clear the ContentType cache.

    Useful in test environments where database state changes between fixture
    setup and test execution (e.g., E2E tests with live_server).
    """
    _content_type_cache.clear()
