"""Deterministic shift assignment — the pure core (design §7).

Everything here is a **pure function** with a precisely enumerated input
surface, so the whole assignment policy is testable in isolation and can
be projected to any future date. No DB, no clock, no RNG. All impure work
(resolving ``enrolled ∩ available``, folding the ``ShiftEvent`` log into
weights, reading materialised rows) lives in the caller and is handed in
as plain values — history and rotation state are just more inputs.

Assignment is a **virtual-time fair rotation** (stride scheduling): every
volunteer carries a clock ``V``; each slot goes to the eligible volunteer
with the lowest ``(V, volunteer_id)``, whose clock then advances by
``1 / weight``. Consequences (asserted in ``tests/test_chore_fairness.py``):
turns are evenly spaced (a rotation, not an independent draw per date),
shares are exactly proportional to weight, and the result is invariant to
input order and reproducible across machines (ties break by id — no hash).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Favour-ledger credit sign per ShiftEvent kind (design §7 event table).
# Positive = did more than their share (weighted toward fewer future
# turns); negative = passed / fell short (weighted toward more). Regular
# ``assigned`` and ``completed`` are neutral.
CREDIT_SIGN: dict[str, int] = {
    "assigned": 0,
    "claimed": 1,
    "covered": 1,
    "inherited": 1,
    "deferred": -1,
    "completed": 0,
    "missed": -1,
}

# Ledger weight bounds. Shares are proportional to weight under the
# rotation, so the clamp means what it says: the most-credited volunteer
# carries half a share, the most-indebted double.
_WEIGHT_STEP = 0.1
_MIN_WEIGHT = 0.5
_MAX_WEIGHT = 2.0

# The rotation state: virtual clock per volunteer. Mutated in place by
# ``advance``/``assign_date`` so a caller can thread one state through a
# date-ordered fold (``chore_projection.fold``).
RotationState = dict[str, float]


def net_credit(events: Iterable[tuple[str, str]]) -> dict[str, int]:
    """Fold ``(kind, volunteer_id)`` events into net favour credit per
    volunteer. Pure — the caller queries the rows. Exhaustively testable
    by enumerating each kind's contribution via ``CREDIT_SIGN``."""
    out: dict[str, int] = {}
    for kind, volunteer_id in events:
        out[volunteer_id] = out.get(volunteer_id, 0) + CREDIT_SIGN.get(kind, 0)
    return out


# "Picked up for others" = help beyond a fair share: a self-claim of an
# open slot (task 06), a voluntary cover (task 12), and slack inherited
# when another volunteer was removed (task 13). Regular ``assigned`` turns
# are the rotation's fair share and counted apart.
_PICKED_UP_KINDS = ("claimed", "covered", "inherited")


@dataclass(frozen=True)
class AccountabilityCounts:
    """A volunteer's accountability split (design §7). ``regular_turns``
    is their rotation-assigned fair share; ``picked_up`` is help beyond it."""

    regular_turns: int = 0
    picked_up: int = 0
    completed: int = 0
    deferred: int = 0
    missed: int = 0


def summarize_accountability(events: Iterable[tuple[str, str]]) -> dict[str, AccountabilityCounts]:
    """Fold ``(kind, volunteer_id)`` events into the per-volunteer
    accountability split. Pure — the caller queries the rows. Reads the
    **same** event stream as ``net_credit`` so the ledger and the display
    provably agree (``net_credit == picked_up - deferred - missed`` per
    volunteer, since the picked-up kinds are exactly the +1-credit ones)."""
    tally: dict[str, dict[str, int]] = {}
    for kind, volunteer_id in events:
        by_kind = tally.setdefault(volunteer_id, {})
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        vid: AccountabilityCounts(
            regular_turns=by_kind.get("assigned", 0),
            picked_up=sum(by_kind.get(k, 0) for k in _PICKED_UP_KINDS),
            completed=by_kind.get("completed", 0),
            deferred=by_kind.get("deferred", 0),
            missed=by_kind.get("missed", 0),
        )
        for vid, by_kind in tally.items()
    }


def weight_from_ledger(credit: int) -> float:
    """Map net favour credit to a bounded rotation weight. More credit
    (did extra) → lower weight (a smaller share); negative credit → a
    larger one. Clamped to ``[_MIN_WEIGHT, _MAX_WEIGHT]``."""
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, 1.0 - _WEIGHT_STEP * credit))


def touch(state: RotationState, volunteer_id: str) -> None:
    """First touch seeds caught-up: a volunteer entering the rotation
    starts at the pool's minimum clock — owed nothing, owing nothing —
    so a newcomer wins turns at their fair rate without a back-pay flood.
    The fold touches every volunteer eligible on a date *before* replaying
    that date's fixed rows, so entering the pool (not being picked) is
    what starts the clock — otherwise a long fixed streak by one volunteer
    would wrongly seed everyone else at their advanced clock."""
    if volunteer_id not in state:
        state[volunteer_id] = min(state.values(), default=0.0)


def advance(state: RotationState, volunteer_id: str, weights: Mapping[str, float]) -> None:
    """One turn taken: advance the volunteer's clock by ``1 / weight``.
    Also applied when replaying a materialised (fixed) assignment, so
    history — including a departed volunteer's ghost id — counts."""
    touch(state, volunteer_id)
    state[volunteer_id] += 1.0 / weights.get(volunteer_id, 1.0)


def assign_date(
    demands: Iterable[tuple[str, Iterable[str], int]],
    state: RotationState,
    weights: Mapping[str, float],
    busy: set[str] | None = None,
) -> dict[str, list[str]]:
    """Jointly assign every free slot of one date, advancing ``state``.
    ``demands`` is one ``(chore_id, eligible_ids, count)`` triple per
    chore; ``busy`` marks volunteers already committed this date (fixed
    assignments), so nobody draws two chores on one day while another
    eligible volunteer is free.

    Chores are processed in scarcity order (fewest eligible first, then
    ``chore_id``). Each slot picks the lowest-clock free volunteer; when
    none is free the pick falls back to the lowest-clock busy one not yet
    on this chore — coverage beats strict no-collision, and a slot stays
    unfilled only when no eligible volunteer remains at all. Per chore,
    acquisition order is the slot index.
    """
    taken = set(busy or ())
    specs = sorted(
        ((chore_id, sorted(set(eligible)), count) for chore_id, eligible, count in demands),
        key=lambda s: (len(s[1]), s[0]),
    )
    for _cid, pool, _count in specs:
        for v in pool:
            touch(state, v)
    out: dict[str, list[str]] = {cid: [] for cid, _, _ in specs}
    for cid, pool, count in specs:
        for _slot in range(max(count, 0)):
            free = [v for v in pool if v not in taken]
            candidates = free or [v for v in pool if v not in out[cid]]
            if not candidates:
                break
            pick = min(candidates, key=lambda v: (state[v], v))
            state[pick] += 1.0 / weights.get(pick, 1.0)
            out[cid].append(pick)
            taken.add(pick)
    return out
