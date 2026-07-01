"""The pure scheduling core (design §7 "The pure core").

Occurrences are a deterministic projection of the pattern; ``Shift`` rows
are a sparse overlay materialised only inside the commit horizon. These
functions are I/O-free and speak small value objects, never ORM rows, so
the whole "which occurrences exist / who is assigned / what to pin or
prune" logic is testable in isolation and reasoned about locally.

- ``occurrences_between`` — the single "what exists" oracle, over
  ``recurrence.occurs_on``. Used by both the tick's pin step and the
  read-side outlook, so confirmed and outlook are the same enumeration.
- ``project`` — maps each occurrence through ``assign_occurrence``.
- ``reconcile`` — where edit-correctness lives: given the pins that exist
  and the freshly-projected assignments, what to insert / prune / keep.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from .chore_assignment import assign_occurrence
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


def project(
    occurrences: Iterable[Occurrence],
    eligible_by_chore: Mapping[str, Sequence[str]],
    weights: Mapping[str, float],
) -> list[ProjectedAssignment]:
    """Assign each occurrence via WRH. Slots of one ``(chore, date)`` are
    filled by the top-ranked eligible volunteers; surplus slots (more
    people than eligible) project to ``None`` (open)."""
    groups: dict[tuple[str, date], list[Occurrence]] = {}
    for occ in occurrences:
        groups.setdefault((occ.chore_id, occ.on_date), []).append(occ)

    out: list[ProjectedAssignment] = []
    for (chore_id, on_date), occs in groups.items():
        occs.sort(key=lambda o: o.slot_index)
        ranked = assign_occurrence(
            eligible_by_chore.get(chore_id, []), weights, chore_id=chore_id, on_date=on_date, count=len(occs)
        )
        for i, occ in enumerate(occs):
            out.append(ProjectedAssignment(occurrence=occ, volunteer_id=ranked[i] if i < len(ranked) else None))
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
