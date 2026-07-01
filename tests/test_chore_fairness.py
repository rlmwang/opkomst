"""Fairness policy — ``services/chore_assignment.pick_assignee``.

Pure, seeded — no DB. Verifies least-loaded selection, tie handling,
the hard ``exclude`` filter, the soft ``avoid_same_day`` filter, and the
empty case.
"""

import random
from collections import Counter

from backend.services.chore_assignment import pick_assignee


def _rng() -> random.Random:
    return random.Random(1234)


def test_none_when_no_eligible():
    assert pick_assignee([], {}, exclude=set(), avoid_same_day=set(), rng=_rng()) is None


def test_none_when_all_excluded():
    assert pick_assignee(["a", "b"], {}, exclude={"a", "b"}, avoid_same_day=set(), rng=_rng()) is None


def test_picks_the_least_loaded():
    # b has the lowest load → always chosen regardless of rng.
    got = pick_assignee(["a", "b", "c"], {"a": 3, "b": 0, "c": 2}, exclude=set(), avoid_same_day=set(), rng=_rng())
    assert got == "b"


def test_ties_stay_within_the_min_load_set():
    # a and b tie at load 0; c is higher and must never be chosen.
    loads = {"a": 0, "b": 0, "c": 5}
    seen = Counter(
        pick_assignee(["a", "b", "c"], loads, exclude=set(), avoid_same_day=set(), rng=random.Random(i))
        for i in range(200)
    )
    assert set(seen) == {"a", "b"}
    assert "c" not in seen


def test_equal_loads_distribute_roughly_evenly():
    loads = {"a": 0, "b": 0}
    seen = Counter(
        pick_assignee(["a", "b"], loads, exclude=set(), avoid_same_day=set(), rng=random.Random(i))
        for i in range(400)
    )
    # Both get a fair share (not one starved); loose bound tolerant of RNG.
    assert seen["a"] > 100 and seen["b"] > 100


def test_exclude_is_a_hard_filter():
    got = pick_assignee(["a", "b"], {"a": 0, "b": 9}, exclude={"a"}, avoid_same_day=set(), rng=_rng())
    assert got == "b"  # a is least-loaded but excluded


def test_avoid_same_day_skipped_when_alternative_exists():
    # a is least-loaded but already busy today → b takes it.
    got = pick_assignee(["a", "b"], {"a": 0, "b": 1}, exclude=set(), avoid_same_day={"a"}, rng=_rng())
    assert got == "b"


def test_avoid_same_day_ignored_when_it_would_leave_nobody():
    # Everyone eligible is already busy → the soft filter yields, and the
    # least-loaded busy person is still chosen rather than returning None.
    got = pick_assignee(["a", "b"], {"a": 0, "b": 5}, exclude=set(), avoid_same_day={"a", "b"}, rng=_rng())
    assert got == "a"
