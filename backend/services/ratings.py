"""Shared rating-aggregation math.

Both the post-event feedback summary and the standalone forms
summary collapse 1..5 rating answers into a 5-bucket distribution
plus a weighted average. The query that produces the
``(value, count)`` rows differs (feedback keys by ``question_key``,
forms by ``question_id``), but the arithmetic is identical and
lives here so it can't drift between the two features.
"""


def rating_distribution(rows: list[tuple[int | None, int]]) -> tuple[list[int], int, float | None]:
    """Collapse ``(value, count)`` rows from a 1..5 rating column into
    a 5-bucket distribution, the total number of responses, and the
    weighted average (``None`` when there are no responses)."""
    distribution = [0, 0, 0, 0, 0]
    total = 0
    weighted = 0
    for value, count in rows:
        if value is None:
            continue
        idx = int(value) - 1
        if 0 <= idx < 5:
            distribution[idx] = int(count)
            total += int(count)
            weighted += int(value) * int(count)
    average = (weighted / total) if total else None
    return distribution, total, average
