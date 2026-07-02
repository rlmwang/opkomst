"""Deterministic shift assignment — the pure core (design §7).

Everything here is a **pure function** with a precisely enumerated input
surface, so the whole assignment policy is testable in isolation and can
be projected to any future date with no stored state. No DB, no clock, no
RNG. All impure work (resolving ``enrolled ∩ available``, folding the
``ShiftEvent`` log into weights) lives in the caller and is handed in as
plain values.

``assign_occurrence`` uses weighted rendezvous (highest-random-weight)
hashing keyed on ``(volunteer_id, chore_id, on_date)``. Its result
depends on ONLY:

1. the occurrence key ``(chore_id, on_date)``;
2. the **set** of eligible volunteer ids;
3. a per-volunteer ``weight`` (default ``1.0``);
4. the ``count`` needed.

Consequences (asserted in ``tests/test_chore_fairness.py``): the result
is invariant to the order of ``eligible`` (it is a function of the set),
reproducible across processes/machines (fixed, unsalted hash over stable
ids), and adding a slot only appends an assignee — the slot index is the
rank, never a hash input.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

# Favour-ledger credit sign per ShiftEvent kind (design §7 event table).
# Positive = did more than their share (weighted toward fewer future
# turns); negative = passed / fell short (weighted toward more). Regular
# ``assigned`` and ``completed`` are neutral. ``covered``/``inherited``
# are emitted by tasks 12/13 but scored here so the map is complete.
CREDIT_SIGN: dict[str, int] = {
    "assigned": 0,
    "claimed": 1,
    "covered": 1,
    "inherited": 1,
    "deferred": -1,
    "completed": 0,
    "missed": -1,
}

# Ledger weight bounds. A gentle, bounded tilt: nobody is ever fully
# starved or saturated regardless of how lopsided their credit gets.
_WEIGHT_STEP = 0.1
_MIN_WEIGHT = 0.5
_MAX_WEIGHT = 2.0

_TWO64 = 2**64


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
# are the WRH fair share and counted apart.
_PICKED_UP_KINDS = ("claimed", "covered", "inherited")


@dataclass(frozen=True)
class AccountabilityCounts:
    """A volunteer's accountability split (design §7). ``regular_turns``
    is their WRH-assigned fair share; ``picked_up`` is help beyond it."""

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
    """Map net favour credit to a bounded WRH weight. More credit (did
    extra) → lower weight (fewer future turns); negative credit → higher
    weight. Clamped to ``[_MIN_WEIGHT, _MAX_WEIGHT]``."""
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, 1.0 - _WEIGHT_STEP * credit))


def _score(volunteer_id: str, chore_id: str, on_date: date, weight: float) -> float:
    """WRH score: ``weight · H`` where ``H`` is a fixed, unsalted hash of
    the occurrence key mapped into ``[0, 1)``. Monotone in weight, uniform
    across volunteers when weights are equal."""
    key = f"{volunteer_id}|{chore_id}|{on_date.isoformat()}".encode()
    h = int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big") / _TWO64
    return weight * h


def assign_occurrence(
    eligible: Iterable[str],
    weights: Mapping[str, float],
    *,
    chore_id: str,
    on_date: date,
    count: int,
) -> list[str]:
    """The top-``count`` volunteer ids for one occurrence, in rank order
    (rank == slot index). Distinct by construction. Returns ``[]`` if
    nobody is eligible or ``count <= 0``.

    Ties on score break by ``volunteer_id`` for total determinism. The
    input is treated as a **set**, so call order never affects the result.
    """
    if count <= 0:
        return []
    pool = set(eligible)
    if not pool:
        return []
    scored = {v: _score(v, chore_id, on_date, weights.get(v, 1.0)) for v in pool}
    ranked = sorted(pool, key=lambda v: (-scored[v], v))
    return ranked[:count]
