"""Deterministic assignment — ``services/chore_assignment`` (design §7).

Pure, no DB, no RNG. Asserts the properties that follow from the minimal
input surface: reproducibility, order-independence, rank-stability, equal
expected share, minimal disruption on membership change, the bounded
ledger weight, and the credit-sign fold.
"""

import random
from collections import Counter
from datetime import date, timedelta

from backend.services.chore_assignment import assign_date, assign_occurrence, net_credit, weight_from_ledger

ELIG = ["alice", "bob", "carol", "dave"]
CHORE = "chore-x"
DAY = date(2026, 1, 7)


def _winners(eligible, weights, dates):
    return {d: assign_occurrence(eligible, weights, chore_id="c", on_date=d, count=1)[0] for d in dates}


def _range(n):
    return [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]


# --- Determinism / reproducibility ---------------------------------------


def test_deterministic_known_answer():
    # A fixed vector so a change to the hash can never pass silently.
    assert assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY) == ["carol", "alice", "dave", "bob"]


def test_repeatable_across_calls():
    a = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    b = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    assert a == b


# --- The input is a SET, not a sequence ----------------------------------


def test_order_independent():
    base = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    for seed in range(20):
        perm = ELIG[:]
        random.Random(seed).shuffle(perm)
        assert assign_occurrence(perm, {}, count=4, chore_id=CHORE, on_date=DAY) == base


def test_duplicates_collapse():
    base = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    assert (
        assign_occurrence(["alice", "alice", "bob", "carol", "dave"], {}, count=4, chore_id=CHORE, on_date=DAY) == base
    )


# --- Rank == slot: raising count only appends ----------------------------


def test_rank_is_prefix_stable():
    full = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    for n in range(len(ELIG) + 1):
        assert assign_occurrence(ELIG, {}, count=n, chore_id=CHORE, on_date=DAY) == full[:n]


def test_empty_and_zero_count():
    assert assign_occurrence([], {}, count=3, chore_id=CHORE, on_date=DAY) == []
    assert assign_occurrence(ELIG, {}, count=0, chore_id=CHORE, on_date=DAY) == []


def test_count_exceeding_pool_returns_all_distinct():
    got = assign_occurrence(["a", "b"], {}, chore_id="c", on_date=date(2026, 1, 7), count=5)
    assert sorted(got) == ["a", "b"]


# --- Fairness: equal expected share --------------------------------------


def test_equal_share_over_many_occurrences():
    dates = _range(1000)
    counts = Counter(_winners(ELIG, {}, dates).values())
    for v in ELIG:
        assert 180 < counts[v] < 320  # ~250 each, generous tolerance


# --- Minimal disruption on membership change (rendezvous property) --------


def test_add_moves_only_newcomer_shifts():
    dates = _range(300)
    before = _winners(ELIG, {}, dates)
    after = _winners([*ELIG, "erin"], {}, dates)
    changed = [d for d in dates if before[d] != after[d]]
    # Every changed date is now won by the newcomer; all others are identical.
    assert all(after[d] == "erin" for d in changed)
    assert all(after[d] == before[d] for d in dates if d not in changed)
    assert 0.1 < len(changed) / len(dates) < 0.35  # ~1/5


def test_remove_moves_only_the_leavers_shifts():
    dates = _range(300)
    before = _winners([*ELIG, "erin"], {}, dates)
    after = _winners(ELIG, {}, dates)  # erin removed
    changed = [d for d in dates if before[d] != after[d]]
    # Only the dates erin used to win change; everyone else is untouched.
    assert all(before[d] == "erin" for d in changed)
    assert all(after[d] == before[d] for d in dates if before[d] != "erin")


# --- Same-day de-collision (assign_date) ----------------------------------

CHORES = ["c1", "c2", "c3"]


def test_single_chore_matches_assign_occurrence():
    for n in range(len(ELIG) + 1):
        got = assign_date([(CHORE, ELIG, n)], {}, on_date=DAY)
        assert got == {CHORE: assign_occurrence(ELIG, {}, chore_id=CHORE, on_date=DAY, count=n)}


def test_no_same_day_double_booking_when_avoidable():
    for d in _range(50):
        got = assign_date([(c, ELIG, 1) for c in CHORES], {}, on_date=d)
        picks = [v for vs in got.values() for v in vs]
        assert len(picks) == len(CHORES) and len(set(picks)) == len(CHORES)


def test_demand_and_pool_order_are_irrelevant():
    base = assign_date([(c, ELIG, 1) for c in CHORES], {}, on_date=DAY)
    for seed in range(10):
        rng = random.Random(seed)
        demands = [(c, rng.sample(ELIG, len(ELIG)), 1) for c in CHORES]
        rng.shuffle(demands)
        assert assign_date(demands, {}, on_date=DAY) == base


def test_shortfall_double_books_rather_than_leaving_open():
    got = assign_date([("c1", ["solo"], 1), ("c2", ["solo"], 1)], {}, on_date=DAY)
    assert got == {"c1": ["solo"], "c2": ["solo"]}


def test_never_twice_on_the_same_chore():
    # c2 wants 3 people from a pool of 2 (both also eligible for c1): the
    # refill pass double-books across chores but never within one, so c2's
    # third slot stays open.
    got = assign_date([("c1", ["a", "b"], 1), ("c2", ["a", "b"], 3)], {}, on_date=DAY)
    assert len(got["c1"]) == 1
    assert sorted(got["c2"]) == ["a", "b"]


# --- Ledger weight -------------------------------------------------------


def test_positive_credit_sinks_a_volunteer():
    base = assign_occurrence(ELIG, {}, count=4, chore_id=CHORE, on_date=DAY)
    assert base[0] == "carol"
    sunk = assign_occurrence(ELIG, {"carol": weight_from_ledger(20)}, count=4, chore_id=CHORE, on_date=DAY)
    assert sunk[0] != "carol"
    assert base.index("carol") < sunk.index("carol")


def test_weight_from_ledger_clamps_and_is_monotone():
    assert weight_from_ledger(0) == 1.0
    assert weight_from_ledger(1000) == 0.5  # floor: did lots extra
    assert weight_from_ledger(-1000) == 2.0  # ceil: owes work
    assert weight_from_ledger(1) < 1.0 < weight_from_ledger(-1)


# --- The credit fold -----------------------------------------------------


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
