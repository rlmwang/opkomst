"""Deterministic assignment — the rotation fold (design §7).

Pure, no DB, no RNG. Asserts the properties the virtual-time fair
rotation promises: determinism and input-order invariance, even spacing
(bounded gaps, no back-to-back turns), exactly proportional shares under
weights, prefix consistency with pinning, history advancing the clocks,
same-day de-collision, the bounded ledger weight, and the credit fold.
"""

import random
from collections import Counter
from datetime import date, timedelta

from backend.services.chore_assignment import assign_date, net_credit, weight_from_ledger
from backend.services.chore_projection import Occurrence, fold

ELIG = ["alice", "bob", "carol", "dave"]
CHORE = "chore-x"
DAY = date(2026, 1, 7)


def _dates(n, step_days=7):
    return [date(2026, 1, 7) + timedelta(days=step_days * i) for i in range(n)]


def _occ(dates, chore=CHORE, slots=1):
    return [Occurrence(chore, d, s) for d in dates for s in range(slots)]


def _winners(occurrences, eligible, weights, fixed=None, state=None):
    chores = {o.chore_id for o in occurrences}
    proj = fold(occurrences, fixed or {}, {c: eligible for c in chores}, weights, state=state)
    return {pa.occurrence: pa.volunteer_id for pa in proj}


# --- Determinism / input-order invariance ---------------------------------


def test_deterministic_and_repeatable():
    occ = _occ(_dates(30))
    assert _winners(occ, ELIG, {}) == _winners(occ, ELIG, {})


def test_order_independent():
    occ = _occ(_dates(30))
    base = _winners(occ, ELIG, {})
    for seed in range(10):
        rng = random.Random(seed)
        perm_elig = ELIG[:]
        rng.shuffle(perm_elig)
        perm_occ = occ[:]
        rng.shuffle(perm_occ)
        assert _winners(perm_occ, perm_elig, {}) == base


def test_duplicate_eligible_ids_collapse():
    occ = _occ(_dates(10))
    assert _winners(occ, ["alice", "alice", "bob", "carol", "dave"], {}) == _winners(occ, ELIG, {})


# --- Even spacing (the rotation property) ----------------------------------


def test_no_back_to_back_turns_and_bounded_gaps():
    occ = _occ(_dates(200))
    seq = [w for _, w in sorted(_winners(occ, ELIG, {}).items(), key=lambda kv: kv[0].on_date)]
    assert all(a != b for a, b in zip(seq, seq[1:], strict=False))  # never twice in a row
    for v in ELIG:
        idx = [i for i, w in enumerate(seq) if w == v]
        gaps = [b - a for a, b in zip(idx, idx[1:], strict=False)]
        assert max(gaps) <= len(ELIG) + 1  # one rotation, plus slack for ties


def test_equal_share_is_exact_not_statistical():
    occ = _occ(_dates(200))
    counts = Counter(_winners(occ, ELIG, {}).values())
    assert max(counts.values()) - min(counts.values()) <= 1


# --- Proportional shares under weights -------------------------------------


def test_weighted_share_is_proportional():
    # Half weight → w/Σw = 0.5/3.5 ≈ 14.3% of turns. The old per-date hash
    # gave ~3% here (polynomial in pool size) — pin that distortion dead.
    n = 700
    counts = Counter(_winners(_occ(_dates(n)), ELIG, {"alice": 0.5}).values())
    expected = n * 0.5 / 3.5
    assert abs(counts["alice"] - expected) <= 0.1 * expected
    assert counts["alice"] < min(counts[v] for v in ELIG if v != "alice")


def test_high_weight_carries_double():
    n = 700
    counts = Counter(_winners(_occ(_dates(n)), ELIG, {"alice": 2.0}).values())
    expected = n * 2.0 / 5.0
    assert abs(counts["alice"] - expected) <= 0.1 * expected


# --- Prefix consistency (pinning and outlook agree) -------------------------


def test_prefix_consistency():
    dates = _dates(60)
    whole = _winners(_occ(dates), ELIG, {})
    state: dict[str, float] = {}
    first = _winners(_occ(dates[:25]), ELIG, {}, state=state)
    rest = _winners(_occ(dates[25:]), ELIG, {}, state=state)
    assert {**first, **rest} == whole


# --- History is an input -----------------------------------------------------


def test_fixed_rows_advance_clocks_and_rest_the_worker():
    dates = _dates(9)
    # Alice already carried the first five turns (claims/covers/whatever):
    fixed = {Occurrence(CHORE, d, 0): "alice" for d in dates[:5]}
    winners = _winners(_occ(dates), ELIG, {}, fixed=fixed)
    free = [winners[Occurrence(CHORE, d, 0)] for d in dates[5:]]
    assert "alice" not in free  # rested until the pool catches up
    assert set(free) == {v for v in ELIG if v != "alice"}  # the others rotate


def test_fixed_rows_are_echoed_not_recomputed():
    dates = _dates(6)
    fixed = {Occurrence(CHORE, dates[2], 0): "dave"}
    winners = _winners(_occ(dates), ELIG, {}, fixed=fixed)
    assert winners[Occurrence(CHORE, dates[2], 0)] == "dave"


def test_ghost_assignee_advances_but_is_never_picked():
    dates = _dates(10)
    fixed = {Occurrence(CHORE, dates[0], 0): "ghost"}
    winners = _winners(_occ(dates), ELIG, {}, fixed=fixed)
    assert "ghost" not in [winners[Occurrence(CHORE, d, 0)] for d in dates[1:]]


def test_newcomer_seeds_caught_up():
    dates = _dates(40)
    state: dict[str, float] = {}
    _winners(_occ(dates[:20]), ELIG, {}, state=state)
    later = _winners(_occ(dates[20:]), [*ELIG, "erin"], {}, state=state)
    seq = [w for _, w in sorted(later.items(), key=lambda kv: kv[0].on_date)]
    # First turn within one rotation of joining — no waiting a season, and
    # no back-pay flood (never twice in a row still holds).
    assert "erin" in seq[: len(ELIG) + 1]
    assert all(a != b for a, b in zip(seq, seq[1:], strict=False))


# --- Same-day de-collision (assign_date, threaded state) --------------------


def test_no_same_day_double_booking_when_avoidable():
    state: dict[str, float] = {}
    for _ in range(50):
        got = assign_date([(c, ELIG, 1) for c in ("c1", "c2", "c3")], state, {})
        picks = [v for vs in got.values() for v in vs]
        assert len(picks) == 3 and len(set(picks)) == 3


def test_shortfall_double_books_rather_than_leaving_open():
    got = assign_date([("c1", ["solo"], 1), ("c2", ["solo"], 1)], {}, {})
    assert got == {"c1": ["solo"], "c2": ["solo"]}


def test_never_twice_on_the_same_chore():
    # c2 wants 3 people from a pool of 2: the refill pass double-books
    # across chores but never within one, so c2's third slot stays open.
    got = assign_date([("c1", ["a", "b"], 1), ("c2", ["a", "b"], 3)], {}, {})
    assert len(got["c1"]) == 1
    assert sorted(got["c2"]) == ["a", "b"]


def test_scarce_chore_is_served_first():
    # b is the only volunteer for c-narrow; c-wide must not grab them.
    got = assign_date([("c-wide", ["a", "b"], 1), ("c-narrow", ["b"], 1)], {}, {})
    assert got["c-narrow"] == ["b"]
    assert got["c-wide"] == ["a"]


def test_fixed_busy_volunteers_are_avoided():
    got = assign_date([("c1", ["a", "b"], 1)], {}, {}, busy={"a"})
    assert got["c1"] == ["b"]


# --- Ledger weight -----------------------------------------------------------


def test_weight_from_ledger_clamps_and_is_monotone():
    assert weight_from_ledger(0) == 1.0
    assert weight_from_ledger(1000) == 0.5  # floor: did lots extra
    assert weight_from_ledger(-1000) == 2.0  # ceil: owes work
    assert weight_from_ledger(1) < 1.0 < weight_from_ledger(-1)


# --- The credit fold ----------------------------------------------------------


def test_net_credit_signs():
    got = net_credit(
        [
            ("assigned", "a"),
            ("completed", "a"),  # a: 0 + 0
            ("claimed", "b"),
            ("covered", "b"),
            ("inherited", "b"),  # b: +1 +1 +1
            ("deferred", "c"),
            ("missed", "c"),  # c: -1 -1
        ]
    )
    assert got == {"a": 0, "b": 3, "c": -2}


def test_net_credit_unknown_kind_is_neutral():
    assert net_credit([("weird", "a")]) == {"a": 0}
