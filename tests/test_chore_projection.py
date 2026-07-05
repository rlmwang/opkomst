"""``chore_projection`` occurrence enumeration + the rotation fold.

Pure, DB-free. ``occurrences_between`` is the single "what exists" oracle;
``fold`` walks it in date order, replaying fixed (materialised) rows and
assigning the rest via the virtual-time rotation.
"""

from datetime import date

from backend.services.chore_projection import ChoreSpec, Occurrence, fold, occurrences_between

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


def test_fold_fills_slots_and_leaves_surplus_open():
    specs = [ChoreSpec("c", (2,), 2)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 7))
    proj = fold(occ, {}, {"c": ["alice"]}, {})  # one eligible, two slots
    by_slot = {p.occurrence.slot_index: p.volunteer_id for p in proj}
    assert by_slot[0] == "alice"
    assert by_slot[1] is None  # surplus slot projects open


def test_fold_assigns_distinct_volunteers_per_occurrence():
    specs = [ChoreSpec("c", (2,), 2)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 7))
    proj = fold(occ, {}, {"c": ["a", "b", "c"]}, {})
    vids = {p.volunteer_id for p in proj}
    assert len(vids) == 2 and None not in vids  # two distinct for two slots


def test_fold_decollides_chores_sharing_a_day():
    specs = [ChoreSpec("c1", (2,), 1), ChoreSpec("c2", (2,), 1)]
    elig = {"c1": ["a", "b"], "c2": ["a", "b"]}
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 3, 2))
    by_date: dict[date, list[str | None]] = {}
    for p in fold(occ, {}, elig, {}):
        by_date.setdefault(p.occurrence.on_date, []).append(p.volunteer_id)
    assert by_date and all(set(v) == {"a", "b"} for v in by_date.values())


def test_fold_is_prefix_consistent():
    # Folding the whole range equals folding a prefix and continuing from
    # the returned state — pinning day-by-day and the whole-window outlook
    # agree.
    specs = [ChoreSpec("c1", (2,), 1), ChoreSpec("c2", (2, 4), 1)]
    elig = {"c1": ["a", "b", "c"], "c2": ["a", "b", "c"]}
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 3, 2))
    whole = {p.occurrence: p.volunteer_id for p in fold(occ, {}, elig, {})}
    cut = date(2026, 2, 1)
    state: dict[str, float] = {}
    before = [o for o in occ if o.on_date <= cut]
    after = [o for o in occ if o.on_date > cut]
    first = {p.occurrence: p.volunteer_id for p in fold(before, {}, elig, {}, state=state)}
    rest = {p.occurrence: p.volunteer_id for p in fold(after, {}, elig, {}, state=state)}
    assert {**first, **rest} == whole


def test_fold_echoes_fixed_and_reassigns_around_them():
    specs = [ChoreSpec("c", (2,), 1)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 2, 2))
    fixed = {occ[0]: "c"}  # someone claimed the first Wednesday
    proj = {p.occurrence: p.volunteer_id for p in fold(occ, fixed, {"c": ["a", "b", "c"]}, {})}
    assert proj[occ[0]] == "c"  # echoed, not recomputed
    assert proj[occ[1]] != "c"  # and the claim counts as a turn taken


def test_fold_replays_pattern_orphaned_fixed_rows_without_echoing():
    specs = [ChoreSpec("c", (2,), 1)]
    occ = occurrences_between(specs, period_weeks=1, starts_on=MON, ends_on=None, start=MON, end=date(2026, 1, 21))
    orphan = Occurrence("c", date(2026, 1, 8), 0)  # a Thursday: no longer produced
    proj = fold(occ, {orphan: "a"}, {"c": ["a", "b"]}, {})
    keys = [p.occurrence for p in proj]
    assert orphan not in keys  # not echoed → reconcile can prune it
    # ...but it advanced a's clock: the Wednesdays around it go to b first.
    by_key = {p.occurrence: p.volunteer_id for p in proj}
    assert by_key[occ[1]] == "b"
