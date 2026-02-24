from django.utils.translation import gettext_lazy as _


def count_active_filters(filters: dict) -> int:
    """Count non-empty filter values.

    Args:
        filters: Dictionary of filter name to value pairs.
                 Values can be strings (single-select) or comma-separated strings (multi-select).

    Returns:
        Number of filters that have non-empty values.
    """
    count = 0
    for value in filters.values():
        if value:
            count += 1
    return count


def build_filter_section(
    name: str,
    label: str,
    filter_type: str,
    choices: list[tuple[str, str]],
    current_value: str,
    empty_label: str = None,
) -> dict:
    """Build a filter section dict for the filters modal component.

    Args:
        name: URL parameter name (e.g., "status", "assignee").
        label: Display label for the filter section.
        filter_type: Either "multi_select" or "single_select".
        choices: List of (value, label) tuples.
        current_value: Current filter value (comma-separated for multi_select).
        empty_label: Label for "no filter" option (single_select only, defaults to "All").

    Returns:
        Dictionary with filter section configuration.
    """
    section = {
        "name": name,
        "label": label,
        "type": filter_type,
        "choices": choices,
        "current_value": current_value or "",
    }
    if filter_type == "single_select" and empty_label:
        section["empty_label"] = empty_label
    return section


def parse_multi_filter(raw_value: str, valid_choices: list[tuple[str, str]]) -> list[str]:
    """Parse a comma-separated filter value into a list of valid values.

    Args:
        raw_value: Comma-separated string of values (e.g., "story,bug").
        valid_choices: List of (value, label) tuples representing valid choices.

    Returns:
        List of valid values found in raw_value. Empty list if raw_value is empty
        or contains no valid values.
    """
    if not raw_value:
        return []
    valid_values = {choice[0] for choice in valid_choices}
    return [v.strip() for v in raw_value.split(",") if v.strip() in valid_values]


def parse_status_filter(raw_value: str, valid_choices: list[tuple[str, str]]) -> list[str]:
    """Parse a comma-separated status filter value into a list of valid status values.

    Args:
        raw_value: Comma-separated string of status values (e.g., "draft,active").
        valid_choices: List of (value, label) tuples representing valid status choices.

    Returns:
        List of valid status values found in raw_value. Empty list if raw_value is empty
        or contains no valid values.
    """
    if not raw_value:
        return []
    valid_values = {choice[0] for choice in valid_choices}
    return [v.strip() for v in raw_value.split(",") if v.strip() in valid_values]


def get_status_filter_label(raw_value: str, choices: list[tuple[str, str]]) -> str:
    """Build a display label for a multi-select status filter.

    Args:
        raw_value: Comma-separated string of status values.
        choices: List of (value, label) tuples for the status choices.

    Returns:
        - Empty string if no valid statuses are selected.
        - The status label if exactly one status is selected.
        - "Status (N)" if N > 1 statuses are selected.
    """
    values = parse_status_filter(raw_value, choices)
    if len(values) == 1:
        return dict(choices).get(values[0], "")
    elif len(values) > 1:
        return _("Status (%(count)d)") % {"count": len(values)}
    return ""
