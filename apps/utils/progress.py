"""Progress calculation utilities."""


def build_progress_dict(done: int, in_progress: int, todo: int, total: int) -> dict | None:
    """Build a progress dict from annotated weight values.

    Args:
        done: Points completed (done status).
        in_progress: Points currently in progress.
        todo: Points remaining (todo status).
        total: Total estimated points.

    Returns:
        A dict with progress percentages and weights, or None if total is 0.
    """
    if total == 0:
        return None

    done_pct = round(done / total * 100)
    in_progress_pct = round(in_progress / total * 100)
    todo_pct = 100 - done_pct - in_progress_pct

    return {
        "done_pct": done_pct,
        "in_progress_pct": in_progress_pct,
        "todo_pct": todo_pct,
        "done_weight": done,
        "in_progress_weight": in_progress,
        "todo_weight": todo,
        "total_weight": total,
    }


def calculate_progress(issues) -> dict | None:
    """Calculate progress based on a list of issues.

    Args:
        issues: Iterable of issue objects with status and estimated_points attributes.

    Returns:
        A dict with progress percentages and weights, or None if total weight is 0.
    """
    if not issues:
        return None

    todo_weight = 0
    in_progress_weight = 0
    done_weight = 0

    for issue in issues:
        weight = getattr(issue, "estimated_points", None) or 1
        category = issue.get_status_category()
        if category == "todo":
            todo_weight += weight
        elif category == "in_progress":
            in_progress_weight += weight
        else:
            done_weight += weight

    total_weight = done_weight + in_progress_weight + todo_weight

    if total_weight == 0:
        return None

    done_pct = round(done_weight / total_weight * 100)
    in_progress_pct = round(in_progress_weight / total_weight * 100)
    todo_pct = 100 - done_pct - in_progress_pct

    return {
        "todo_pct": todo_pct,
        "in_progress_pct": in_progress_pct,
        "done_pct": done_pct,
        "todo_weight": todo_weight,
        "in_progress_weight": in_progress_weight,
        "done_weight": done_weight,
        "total_weight": total_weight,
    }
