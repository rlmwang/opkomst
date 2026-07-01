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


def first_cycle_monday(starts_on: date) -> date:
    """The Monday cycle index 0 anchors on: the first Monday on or after
    the roster's ``starts_on``. Derived from the interval, never stored."""
    return starts_on + timedelta(days=(7 - starts_on.weekday()) % 7)


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
    - k > 1: the cycle anchors on ``first_cycle_monday(starts_on)`` (the
      first Monday within the interval), which is cycle week 0. The offset
      is ``(d - anchor).days % (7 * k)``; Python's modulo wraps negatives,
      so the partial week between ``starts_on`` and that first Monday
      takes the pattern of the cycle's *last* week.
    """
    if not cycle_slots:
        return False
    if period_weeks <= 1:
        return d.weekday() in cycle_slots
    anchor = first_cycle_monday(starts_on)
    offset = (d - anchor).days % (7 * period_weeks)
    return offset in cycle_slots
