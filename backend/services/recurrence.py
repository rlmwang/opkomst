"""Pure recurrence math for chore rosters.

The single source of truth for "does a chore fall on this date". A chore
recurs on a **k-week cycle** (``period_weeks``); its ``cycle_slots`` are
flat offsets ``week_index*7 + weekday`` into that cycle, range
``0 .. 7*period_weeks - 1``, **Mon=0** (Python ``date.weekday()``).

Kept DB-free and pure so it's the same logic the shift generator
(``services/chore_tick.py``) and any preview/validation share, and so it
is exhaustively unit-testable (``tests/test_chore_recurrence.py``).
"""

from collections.abc import Sequence
from datetime import date


def occurs_on(
    d: date,
    *,
    cycle_slots: Sequence[int],
    period_weeks: int,
    anchor_monday: date | None,
) -> bool:
    """Whether a chore with ``cycle_slots`` on a ``period_weeks``-week
    cycle occurs on date ``d``.

    - k <= 1: weekly — ``d.weekday() in cycle_slots``.
    - k > 1: ``anchor_monday`` (a Monday) anchors cycle index 0. Dates
      before the anchor never occur; otherwise the offset is
      ``(d - anchor_monday).days % (7 * period_weeks)``.

    Raises ``ValueError`` if ``period_weeks > 1`` without an anchor.
    """
    if not cycle_slots:
        return False
    if period_weeks <= 1:
        return d.weekday() in cycle_slots
    if anchor_monday is None:
        raise ValueError("anchor_monday is required when period_weeks > 1")
    if d < anchor_monday:
        return False
    offset = (d - anchor_monday).days % (7 * period_weeks)
    return offset in cycle_slots
