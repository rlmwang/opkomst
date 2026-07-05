"""The pure scheduling core (design §7 "The pure core").

Occurrences are a deterministic projection of the pattern; ``Shift`` rows
are a sparse overlay materialised only inside the commit horizon. These
functions are I/O-free and speak small value objects, never ORM rows, so
the whole "which occurrences exist / who is assigned / what to pin or
prune" logic is testable in isolation and reasoned about locally.

- ``occurrences_between`` — the single "what exists" oracle, over
  ``recurrence.occurs_on``. Used by both the tick's pin step and the
  read-side outlook, so confirmed and outlook are the same enumeration.
- ``fold`` — the virtual-time fair rotation: walks the dates in order,
  replaying materialised (fixed) assignments into the clocks and picking
  the free slots via ``assign_date``.
- ``reconcile`` — where edit-correctness lives: given the pins that exist
  and the freshly-projected assignments, what to insert / prune / keep.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .chore_assignment import RotationState, advance, assign_date, touch
from .recurrence import occurs_on


@dataclass(frozen=True)
class ChoreSpec:
    """The pattern inputs for one chore (DB-free)."""

    chore_id: str
    cycle_slots: tuple[int, ...]
    people_per_shift: int


@dataclass(frozen=True)
class Occurrence:
    """A single materialisable slot. Its natural key ``(chore_id, on_date,
    slot_index)`` is derivable from the pattern, so an overlay row slots
    back into the projection unambiguously."""

    chore_id: str
    on_date: date
    slot_index: int


@dataclass(frozen=True)
class ProjectedAssignment:
    occurrence: Occurrence
    volunteer_id: str | None  # None = no eligible volunteer (an open slot)


@dataclass(frozen=True)
class PinnedShift:
    """A materialised shift, projected down to only what ``reconcile``
    needs: its key, whether it has been reminded or acted on (a commitment
    we must honour), and its current assignee."""

    key: Occurrence
    status: str
    reminded: bool
    acted: bool
    assignee: str | None


@dataclass(frozen=True)
class Diff:
    insert: list[ProjectedAssignment]  # projected occurrences with no pin yet
    prune: list[Occurrence]  # stale, un-acted pins to drop


def occurrences_between(
    chores: Sequence[ChoreSpec],
    *,
    period_weeks: int,
    starts_on: date,
    ends_on: date | None,
    start: date,
    end: date,
) -> list[Occurrence]:
    """Every occurrence in ``[start, end]`` (floored by ``starts_on``,
    capped by ``ends_on``). Pure over the pattern; no DB."""
    lo = max(start, starts_on)
    hi = end if ends_on is None else min(end, ends_on)
    out: list[Occurrence] = []
    d = lo
    while d <= hi:
        for chore in chores:
            if occurs_on(d, cycle_slots=chore.cycle_slots, period_weeks=period_weeks, starts_on=starts_on):
                out.extend(Occurrence(chore.chore_id, d, slot) for slot in range(chore.people_per_shift))
        d += timedelta(days=1)
    return out


def _available(volunteer_id: str, on_date: date, unavailable: Mapping[str, Sequence[tuple[date, date]]]) -> bool:
    return not any(lo <= on_date <= hi for lo, hi in unavailable.get(volunteer_id, ()))


def fold(
    occurrences: Iterable[Occurrence],
    fixed: Mapping[Occurrence, str | None],
    eligible_by_chore: Mapping[str, Sequence[str]],
    weights: Mapping[str, float],
    unavailable: Mapping[str, Sequence[tuple[date, date]]] | None = None,
    state: RotationState | None = None,
) -> list[ProjectedAssignment]:
    """The virtual-time fair rotation (design §7). Walks the union of
    enumerated occurrences and ``fixed`` (materialised ``occurrence →
    assignee``) in date order. Per date: every fixed assignee's clock
    advances and they count as busy — history is an input, never
    recomputed, and it replays even when a pattern edit no longer
    produces its occurrence (such rows advance clocks but are not
    echoed, so ``reconcile`` can still prune them). The remaining free
    slots are picked by ``assign_date`` among the volunteers **available**
    that date; surplus slots project to ``None`` (open).

    Prefix-consistent: pass ``state`` back in to continue a fold from
    where a previous one stopped — folding ``[a, c]`` equals folding
    ``[a, b]`` and continuing over ``(b, c]``.
    """
    away = unavailable or {}
    clocks: RotationState = state if state is not None else {}
    enumerated = list(occurrences)
    free_by_date: dict[date, dict[str, list[Occurrence]]] = {}
    for occ in enumerated:
        if occ not in fixed:
            free_by_date.setdefault(occ.on_date, {}).setdefault(occ.chore_id, []).append(occ)
    fixed_by_date: dict[date, list[Occurrence]] = {}
    for occ in fixed:
        fixed_by_date.setdefault(occ.on_date, []).append(occ)
    enumerated_set = set(enumerated)

    out: list[ProjectedAssignment] = []
    for on_date in sorted(free_by_date.keys() | fixed_by_date.keys()):
        # Everyone eligible on this date enters the rotation *now* (seeded
        # caught-up), before any of the date's rows advance a clock: being
        # in the pool starts your clock, being picked advances it.
        day_chores = {o.chore_id for o in fixed_by_date.get(on_date, ())} | free_by_date.get(on_date, {}).keys()
        for cid in sorted(day_chores):
            for v in eligible_by_chore.get(cid, ()):
                touch(clocks, v)
        busy: set[str] = set()
        taken_by_chore: dict[str, set[str]] = {}
        for occ in sorted(fixed_by_date.get(on_date, ()), key=lambda o: (o.chore_id, o.slot_index)):
            assignee = fixed[occ]
            if assignee is not None:
                advance(clocks, assignee, weights)
                busy.add(assignee)
                taken_by_chore.setdefault(occ.chore_id, set()).add(assignee)
            if occ in enumerated_set:
                out.append(ProjectedAssignment(occurrence=occ, volunteer_id=assignee))
        chores = free_by_date.get(on_date, {})
        demands = [
            (
                chore_id,
                [
                    v
                    for v in eligible_by_chore.get(chore_id, [])
                    if _available(v, on_date, away) and v not in taken_by_chore.get(chore_id, ())
                ],
                len(occs),
            )
            for chore_id, occs in chores.items()
        ]
        assigned = assign_date(demands, clocks, weights, busy=busy)
        for chore_id, occs in chores.items():
            occs.sort(key=lambda o: o.slot_index)
            picks = assigned[chore_id]
            for i, occ in enumerate(occs):
                out.append(ProjectedAssignment(occurrence=occ, volunteer_id=picks[i] if i < len(picks) else None))
    return out


def reconcile(existing: Sequence[PinnedShift], projected: Sequence[ProjectedAssignment], *, today: date) -> Diff:
    """The edit-correctness function. Rules:

    - a projected occurrence with no pin → **insert**;
    - a pin no longer projected that is un-acted and not reminded (still
      just cache) → **prune**;
    - a reminded or acted pin, or one still projected → **keep** (an
      existing valid pin keeps its assignee: promises don't reshuffle);
    - ``on_date < today`` → **never touched** (the frozen past).
    """
    projected_keys = {pa.occurrence for pa in projected}
    existing_keys = {p.key for p in existing}
    insert = [pa for pa in projected if pa.occurrence not in existing_keys]
    prune = [
        p.key
        for p in existing
        if p.key.on_date >= today and p.key not in projected_keys and not p.acted and not p.reminded
    ]
    return Diff(insert=insert, prune=prune)
