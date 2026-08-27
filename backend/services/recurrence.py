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
from datetime import date, timedelta


def cycle_anchor_monday(starts_on: date) -> date:
    """The Monday cycle index 0 anchors on: the Monday of the week that
    contains ``starts_on``. The start date is always inside cycle week 0,
    so the first week of a k-week cycle is the week the thing begins and a
    weekday ticked in the grid's first row means the one in that week.
    Derived from the interval, never stored."""
    return starts_on - timedelta(days=starts_on.weekday())


def occurs_on(
    d: date,
    *,
    cycle_slots: Sequence[int],
    period_weeks: int,
    starts_on: date,
) -> bool:
    """Whether a chore with ``cycle_slots`` on a ``period_weeks``-week
    cycle occurs on date ``d``.

    - k <= 1: weekly — ``d.weekday() in cycle_slots``.
    - k > 1: the cycle anchors on ``cycle_anchor_monday(starts_on)`` (the
      Monday of the starting week), which is cycle week 0. The offset is
      ``(d - anchor).days % (7 * k)``. Callers enumerate from ``starts_on``
      onwards, so the days before it in that first week never come up.
    """
    if not cycle_slots:
        return False
    if period_weeks <= 1:
        return d.weekday() in cycle_slots
    anchor = cycle_anchor_monday(starts_on)
    offset = (d - anchor).days % (7 * period_weeks)
    return offset in cycle_slots
