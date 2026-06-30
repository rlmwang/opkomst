"""Recurrence math — ``services/recurrence.py::occurs_on``.

Pure, no DB. The cycle convention: offset = week_index*7 + weekday,
Mon=0. Anchor 2026-01-05 is a Monday; the dates below are picked
relative to it.
"""

from datetime import date

import pytest

from backend.services.recurrence import occurs_on

ANCHOR = date(2026, 1, 5)  # a Monday
WED_WEEK_A = date(2026, 1, 7)  # anchor + 2 days  → offset 2
WED_WEEK_B = date(2026, 1, 14)  # anchor + 9 days  → offset 9
WED_NEXT_CYCLE_A = date(2026, 1, 21)  # anchor + 16 → 16 % 14 == 2
SUN_BEFORE_ANCHOR = date(2026, 1, 4)


def test_anchor_is_a_monday():
    assert ANCHOR.weekday() == 0


# --- Weekly (k = 1): plain weekday match -----------------------------


def test_weekly_hits_listed_weekday():
    # Wednesday = 2; Friday = 4.
    assert occurs_on(WED_WEEK_A, cycle_slots=[2, 4], period_weeks=1, anchor_monday=None)


def test_weekly_misses_unlisted_weekday():
    # Wednesday is not Monday(0) or Friday(4).
    assert not occurs_on(WED_WEEK_A, cycle_slots=[0, 4], period_weeks=1, anchor_monday=None)


def test_weekly_ignores_anchor():
    # k=1 needs no anchor; weekday alone decides.
    assert occurs_on(WED_WEEK_B, cycle_slots=[2], period_weeks=1, anchor_monday=None)


# --- Biweekly (k = 2): alternating weeks -----------------------------


def test_biweekly_week_a_slot_hits_only_week_a():
    # cycle_slots=[2] means "Wednesday of week A".
    assert occurs_on(WED_WEEK_A, cycle_slots=[2], period_weeks=2, anchor_monday=ANCHOR)
    assert not occurs_on(WED_WEEK_B, cycle_slots=[2], period_weeks=2, anchor_monday=ANCHOR)


def test_biweekly_week_b_slot_hits_only_week_b():
    # cycle_slots=[9] means "Wednesday of week B" (7 + 2).
    assert not occurs_on(WED_WEEK_A, cycle_slots=[9], period_weeks=2, anchor_monday=ANCHOR)
    assert occurs_on(WED_WEEK_B, cycle_slots=[9], period_weeks=2, anchor_monday=ANCHOR)


def test_biweekly_wraps_at_cycle_boundary():
    # Two weeks after week-A Wednesday is week-A again (offset 16 % 14 == 2).
    assert occurs_on(WED_NEXT_CYCLE_A, cycle_slots=[2], period_weeks=2, anchor_monday=ANCHOR)


def test_dates_before_anchor_never_occur():
    assert not occurs_on(SUN_BEFORE_ANCHOR, cycle_slots=[2, 6], period_weeks=2, anchor_monday=ANCHOR)


def test_k_gt_1_without_anchor_raises():
    with pytest.raises(ValueError):
        occurs_on(WED_WEEK_A, cycle_slots=[2], period_weeks=2, anchor_monday=None)


# --- Edge ------------------------------------------------------------


def test_empty_cycle_slots_never_occurs():
    assert not occurs_on(WED_WEEK_A, cycle_slots=[], period_weeks=1, anchor_monday=None)
    assert not occurs_on(WED_WEEK_A, cycle_slots=[], period_weeks=2, anchor_monday=ANCHOR)
