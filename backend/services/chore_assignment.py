"""Fair shift assignment — the pure core.

``pick_assignee`` is deliberately DB-free: it takes the eligible
volunteer ids, their current loads, and the constraint sets, and returns
who should take a shift. Purity makes the fairness policy exhaustively
seed-testable (``tests/test_chore_fairness.py``) and keeps the tick
(``services/chore_tick.py``) as the only place that touches the DB.

Policy: greedy least-loaded. Among the eligible volunteers (minus the
hard ``exclude`` set), prefer those not already busy that day
(``avoid_same_day``) *when that still leaves a choice*, then pick
uniformly at random among the least-loaded of the remaining pool. Ties
are drawn from the ``rng`` the caller supplies, so the result is
reproducible under a seeded ``random.Random``.
"""

import random
from collections.abc import Mapping, Sequence


def pick_assignee(
    eligible: Sequence[str],
    loads: Mapping[str, int],
    *,
    exclude: set[str],
    avoid_same_day: set[str],
    rng: random.Random,
) -> str | None:
    """Choose a volunteer for one shift, or ``None`` if nobody is
    eligible. ``exclude`` is a hard filter (e.g. the person handing the
    shift off); ``avoid_same_day`` is a soft filter, applied only while
    it leaves at least one candidate."""
    pool = [v for v in eligible if v not in exclude]
    if not pool:
        return None

    # Soft constraint: skip people already assigned that day, but only if
    # doing so still leaves someone.
    not_busy = [v for v in pool if v not in avoid_same_day]
    if not_busy:
        pool = not_busy

    least = min(loads.get(v, 0) for v in pool)
    contenders = sorted(v for v in pool if loads.get(v, 0) == least)
    return rng.choice(contenders)
