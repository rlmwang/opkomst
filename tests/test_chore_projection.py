"""``chore_projection`` occurrence enumeration + assignment (task 11).

Pure, DB-free. ``occurrences_between`` is the single "what exists" oracle;
``project`` maps it through the deterministic WRH assignment.
"""

from datetime import date

from backend.services.chore_projection import ChoreSpec, occurrences_between, project

MON = date(2026, 1, 5)  # a Monday


def _dates(occ):
    return [o.on_date for o in occ]


def test_weekly_enumerates_the_pattern():
    specs = [ChoreSpec("c", (2,), 1)]  # Wednesday
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 26))
    assert _dates(occ) == [date(2026, 1, 7), date(2026, 1, 14), date(2026, 1, 21)]


def test_floored_by_starts_on_and_capped_by_ends_on():
    specs = [ChoreSpec("c", (2,), 1)]
    occ = occurrences_between(
        specs, period_weeks=1, starts_on=date(2026, 1, 10), ends_on=date(2026, 1, 20), start=MON, end=date(2026, 2, 1)
    )
    assert _dates(occ) == [date(2026, 1, 14)]  # only the Wednesday within [10, 20]


def test_people_per_shift_expands_to_slots():
    specs = [ChoreSpec("c", (2,), 2)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 7))
    assert sorted(o.slot_index for o in occ) == [0, 1]


def test_project_fills_slots_and_leaves_surplus_open():
    specs = [ChoreSpec("c", (2,), 2)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 7))
    proj = project(occ, {"c": ["alice"]}, {})  # one eligible, two slots
    by_slot = {p.occurrence.slot_index: p.volunteer_id for p in proj}
    assert by_slot[0] == "alice"
    assert by_slot[1] is None  # surplus slot projects open


def test_project_assigns_distinct_volunteers_per_occurrence():
    specs = [ChoreSpec("c", (2,), 2)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 7))
    proj = project(occ, {"c": ["a", "b", "c"]}, {})
    vids = {p.volunteer_id for p in proj}
    assert len(vids) == 2 and None not in vids  # two distinct for two slots


def test_project_is_order_independent():
    specs = [ChoreSpec("c", (2,), 1)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 2, 2))
    a = {(p.occurrence.on_date): p.volunteer_id for p in project(occ, {"c": ["a", "b", "c"]}, {})}
    b = {(p.occurrence.on_date): p.volunteer_id for p in project(occ, {"c": ["c", "b", "a"]}, {})}
    assert a == b
