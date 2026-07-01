"""Recurrence math — ``services/recurrence.py::occurs_on``.

Pure, no DB. Cycle convention: offset = week_index*7 + weekday, Mon=0.
When k>1 the cycle anchors on the first Monday on/after ``starts_on``.
"""

from datetime import date

from backend.services.recurrence import first_cycle_monday, occurs_on

MON = date(2026, 1, 5)  # a Monday — start on a Monday, so anchor == start
WED_WEEK_A = date(2026, 1, 7)  # anchor + 2  → offset 2
WED_WEEK_B = date(2026, 1, 14)  # anchor + 9  → offset 9
WED_NEXT_CYCLE_A = date(2026, 1, 21)  # anchor + 16 → 16 % 14 == 2


# --- first_cycle_monday ----------------------------------------------


def test_first_cycle_monday_of_a_monday_is_itself():
    assert first_cycle_monday(MON) == MON


def test_first_cycle_monday_rolls_forward():
    assert first_cycle_monday(date(2026, 1, 7)) == date(2026, 1, 12)  # Wed → next Mon
    assert first_cycle_monday(date(2026, 1, 4)) == MON  # Sun → Mon


# --- Weekly (k = 1): plain weekday match -----------------------------


def test_weekly_hits_listed_weekday():
    # Wednesday = 2; Friday = 4.
    assert occurs_on(WED_WEEK_A, cycle_slots=[2, 4], period_weeks=1, starts_on=MON)


def test_weekly_misses_unlisted_weekday():
    assert not occurs_on(WED_WEEK_A, cycle_slots=[0, 4], period_weeks=1, starts_on=MON)


def test_weekly_ignores_start():
    # k=1 needs no anchor; weekday alone decides regardless of starts_on.
    assert occurs_on(WED_WEEK_B, cycle_slots=[2], period_weeks=1, starts_on=date(2020, 1, 1))


# --- Biweekly (k = 2): alternating weeks, anchored at first Monday ---


def test_biweekly_week_a_slot_hits_only_week_a():
    # cycle_slots=[2] means "Wednesday of week A".
    assert occurs_on(WED_WEEK_A, cycle_slots=[2], period_weeks=2, starts_on=MON)
    assert not occurs_on(WED_WEEK_B, cycle_slots=[2], period_weeks=2, starts_on=MON)


def test_biweekly_week_b_slot_hits_only_week_b():
    # cycle_slots=[9] means "Wednesday of week B" (7 + 2).
    assert not occurs_on(WED_WEEK_A, cycle_slots=[9], period_weeks=2, starts_on=MON)
    assert occurs_on(WED_WEEK_B, cycle_slots=[9], period_weeks=2, starts_on=MON)


def test_biweekly_wraps_at_cycle_boundary():
    # Two weeks after week-A Wednesday is week-A again (offset 16 % 14 == 2).
    assert occurs_on(WED_NEXT_CYCLE_A, cycle_slots=[2], period_weeks=2, starts_on=MON)


# --- Partial first week (start not a Monday) uses the LAST cycle week -


def test_partial_first_week_takes_last_week_pattern():
    start = date(2026, 1, 7)  # Wednesday; first cycle Monday is 5 days later
    assert first_cycle_monday(start) == date(2026, 1, 12)
    # The opening Wednesday sits in the partial pre-anchor week, so it
    # takes week B's pattern (offset 9), not week A's (offset 2).
    assert occurs_on(start, cycle_slots=[9], period_weeks=2, starts_on=start)
    assert not occurs_on(start, cycle_slots=[2], period_weeks=2, starts_on=start)


# --- Edge ------------------------------------------------------------


def test_empty_cycle_slots_never_occurs():
    assert not occurs_on(WED_WEEK_A, cycle_slots=[], period_weeks=1, starts_on=MON)
    assert not occurs_on(WED_WEEK_A, cycle_slots=[], period_weeks=2, starts_on=MON)
