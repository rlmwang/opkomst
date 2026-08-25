"""Shift pinning + reconciliation — the daily ``roster-tick`` (design §7).

Occurrences are a deterministic projection of the pattern; ``Shift`` rows
are a sparse overlay materialised only inside the commit horizon. Per
**running** roster, ``run_tick``:

1. **pins the incoming edge** — for each occurrence in
   ``[today, today+commit_horizon_days]`` with no row yet, insert a pinned
   Shift (assigned by the rotation fold, or ``open`` if nobody eligible);
2. **prunes stale pins (window-only)** — drop un-acted, un-reminded pins
   whose occurrence no longer projects (a roster edit orphaned them);
3. **reconciles the past** — ``scheduled`` shifts before today that were
   never marked done flip to ``missed``.

A ``forming`` roster (``activated_at`` is NULL) is skipped entirely, so
nothing is pinned or promised until the organiser starts it. The pin/prune
decision is the pure ``chore_projection`` core; the only impure steps are
resolving eligibility and the favour ledger (``ledger_weights``).

``reassign_shift`` is the single-shift variant used by the handoff route.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Chore, Enrollment, Roster, Shift, ShiftEvent, Volunteer, VolunteerAvailability
from . import tenancy
from .chore_assignment import RotationState, net_credit, weight_from_ledger
from .chore_projection import ChoreSpec, Diff, Occurrence, PinnedShift, fold, occurrences_between, reconcile


def record_event(db: Session, *, roster_id: str, volunteer_id: str, kind: str, shift_id: str | None = None) -> None:
    """Append one accountability event. The single write-point for the
    ShiftEvent log, used by the tick and the public shift-action routes."""
    db.add(ShiftEvent(roster_id=roster_id, volunteer_id=volunteer_id, kind=kind, shift_id=shift_id))


def release_shift(db: Session, *, roster_id: str, volunteer_id: str, shift: Shift) -> None:
    """Hand a confirmed shift back: record the give-up (``deferred``),
    unassign it, and mark it ``open`` for anyone to claim — no automatic
    reassignment. Shared by "can't make it", time-off overlap, and dropping a
    chore from the enrolment. Clears the
    sent stamp so whoever picks it up next gets their own reminder."""
    record_event(db, roster_id=roster_id, volunteer_id=volunteer_id, kind="deferred", shift_id=shift.id)
    shift.volunteer_id = None
    shift.status = "open"
    shift.reminder_sent_at = None


def ledger_weights(db: Session, roster_id: str) -> dict[str, float]:
    """Resolve the favour ledger for a roster into WRH weights. Thin impure
    wrapper: query the ``ShiftEvent`` rows, hand them to the pure
    ``net_credit`` fold, map each through ``weight_from_ledger``. Volunteers
    with no events are absent and default to weight 1.0 at lookup time."""
    rows = db.query(ShiftEvent.kind, ShiftEvent.volunteer_id).filter(ShiftEvent.roster_id == roster_id).all()
    credit = net_credit((kind, vid) for kind, vid in rows)
    return {vid: weight_from_ledger(c) for vid, c in credit.items()}


def _day_assignments(
    db: Session, roster_id: str, on_date: date, *, exclude_shift_id: str | None = None
) -> list[tuple[str, str]]:
    """``(volunteer_id, chore_id)`` for every scheduled shift of the
    roster on one date — the same-day picture ``reassign_shift`` needs."""
    q = (
        db.query(Shift.volunteer_id, Shift.chore_id)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(
            Chore.roster_id == roster_id,
            Shift.on_date == on_date,
            Shift.status == "scheduled",
            Shift.volunteer_id.is_not(None),
        )
    )
    if exclude_shift_id is not None:
        q = q.filter(Shift.id != exclude_shift_id)
    return [(vid, cid) for vid, cid in q.all()]


def reassign_shift(db: Session, shift: Shift, *, exclude: set[str] | None = None, kind: str = "assigned") -> str | None:
    """Assign a single ``open`` shift. Ranks by the rotation's clocks
    folded up to the shift's date (this shift excluded), picks the
    lowest-clock eligible volunteer who is not excluded, preferring one
    with no other shift on this date (same-day de-collision, design §7);
    never someone already on another slot of this occurrence. Records
    ``kind`` for the chosen volunteer and returns their id, or ``None``.
    ``kind`` is ``assigned`` for a plain re-cover, ``inherited`` when
    covering a departed volunteer's slot. Does not commit."""
    chore = db.query(Chore).filter(Chore.id == shift.chore_id).first()
    if chore is None:
        return None
    eligible = [row[0] for row in db.query(Enrollment.volunteer_id).filter(Enrollment.chore_id == shift.chore_id).all()]
    if not eligible:
        return None
    day = _day_assignments(db, chore.roster_id, shift.on_date, exclude_shift_id=shift.id)
    skip = set(exclude or set()) | {vid for vid, cid in day if cid == shift.chore_id}
    busy = {vid for vid, _ in day}
    roster = db.query(Roster).filter(Roster.id == chore.roster_id).one()
    chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
    clocks: RotationState = {}
    _fold_range(db, roster, chores, shift.on_date, exclude_shift_id=shift.id, state=clocks)
    floor = min(clocks.values(), default=0.0)
    candidates = sorted((v for v in eligible if v not in skip), key=lambda v: (clocks.get(v, floor), v))
    chosen = next((v for v in candidates if v not in busy), candidates[0] if candidates else None)
    if chosen is not None:
        shift.volunteer_id = chosen
        shift.status = "scheduled"
        record_event(db, roster_id=chore.roster_id, volunteer_id=chosen, kind=kind, shift_id=shift.id)
    return chosen


def cover_orphaned_shifts(db: Session, roster_id: str, today: date) -> int:
    """Re-cover every future pinned shift left unassigned (volunteer_id
    NULL, still ``scheduled``) — e.g. after a volunteer leaves and their
    shifts SET NULL. Each is reassigned via WRH among the remaining
    eligible (an ``inherited`` pickup, +credit); if nobody is eligible it
    becomes ``open`` for anyone to claim. Immediate coverage, not the
    tick's job. Returns how many were re-covered. Does not commit."""
    orphans = (
        db.query(Shift)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(
            Chore.roster_id == roster_id,
            Shift.on_date >= today,
            Shift.status == "scheduled",
            Shift.volunteer_id.is_(None),
        )
        .all()
    )
    covered = 0
    for shift in orphans:
        shift.reminder_sent_at = None
        if reassign_shift(db, shift, kind="inherited") is None:
            shift.status = "open"
        else:
            covered += 1
    db.flush()
    return covered


# Acquisition/outcome events that make a pin a real commitment — an
# orphaned pin carrying one of these is kept, not pruned.
_ACTED_KINDS = ("claimed", "covered", "completed", "inherited")


def _eligible_by_chore(db: Session, chore_ids: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not chore_ids:
        return out
    for cid, vid in (
        db.query(Enrollment.chore_id, Enrollment.volunteer_id).filter(Enrollment.chore_id.in_(chore_ids)).all()
    ):
        out.setdefault(cid, []).append(vid)
    return out


def _chore_specs(chores: list[Chore]) -> list[ChoreSpec]:
    return [
        ChoreSpec(chore_id=c.id, cycle_slots=tuple(c.cycle_slots), people_per_shift=c.people_per_shift) for c in chores
    ]


def horizon_end(roster: Roster, today: date) -> date:
    end = today + timedelta(days=roster.commit_horizon_days)
    if roster.ends_on is not None and roster.ends_on < end:
        end = roster.ends_on
    return end


def _window_pins(
    db: Session, roster_id: str, chore_ids: list[str], today: date, end: date
) -> tuple[list[PinnedShift], dict[Occurrence, Shift]]:
    """Load the pinned shifts in ``[today, end]`` as value objects plus a
    ``{key: row}`` map for applying prunes. ``acted`` folds in reminded,
    done, and any claim/cover/inherit event on the shift."""
    if not chore_ids:
        return [], {}
    acted_ids = {
        sid
        for (sid,) in db.query(ShiftEvent.shift_id)
        .filter(
            ShiftEvent.roster_id == roster_id,
            ShiftEvent.kind.in_(_ACTED_KINDS),
            ShiftEvent.shift_id.is_not(None),
        )
        .all()
    }
    rows = db.query(Shift).filter(Shift.chore_id.in_(chore_ids), Shift.on_date >= today, Shift.on_date <= end).all()
    pins: list[PinnedShift] = []
    row_by_key: dict[Occurrence, Shift] = {}
    for s in rows:
        key = Occurrence(s.chore_id, s.on_date, s.slot_index)
        row_by_key[key] = s
        acted = s.status == "done" or s.reminder_sent_at is not None or s.id in acted_ids
        pins.append(
            PinnedShift(
                key=key, status=s.status, reminded=s.reminder_sent_at is not None, acted=acted, assignee=s.volunteer_id
            )
        )
    return pins, row_by_key


def _apply(db: Session, roster_id: str, diff: Diff, row_by_key: dict[Occurrence, Shift]) -> int:
    for key in diff.prune:
        db.delete(row_by_key[key])
    inserted = 0
    for pa in diff.insert:
        occ = pa.occurrence
        shift = Shift(
            chore_id=occ.chore_id,
            on_date=occ.on_date,
            slot_index=occ.slot_index,
            status="scheduled" if pa.volunteer_id else "open",
            volunteer_id=pa.volunteer_id,
        )
        db.add(shift)
        db.flush()
        if pa.volunteer_id:
            record_event(db, roster_id=roster_id, volunteer_id=pa.volunteer_id, kind="assigned", shift_id=shift.id)
        inserted += 1
    db.flush()
    return inserted


def _unavailable(db: Session, roster_id: str) -> dict[str, list[tuple[date, date]]]:
    """Per-volunteer away ranges for a roster (design §7 availability)."""
    out: dict[str, list[tuple[date, date]]] = {}
    rows = (
        db.query(VolunteerAvailability.volunteer_id, VolunteerAvailability.start_date, VolunteerAvailability.end_date)
        .join(Volunteer, Volunteer.id == VolunteerAvailability.volunteer_id)
        .filter(Volunteer.roster_id == roster_id)
        .all()
    )
    for vid, start, end in rows:
        out.setdefault(vid, []).append((start, end))
    return out


def _fixed_rows(db: Session, chore_ids: list[str], end: date, *, exclude_shift_id: str | None = None):
    """Every materialised shift up to ``end`` as the fold's fixed stream
    (``occurrence → assignee``). Provenance doesn't matter — tick-assigned,
    claimed, covered, handed over — and neither does whether the current
    pattern still produces the occurrence: history replays regardless."""
    if not chore_ids:
        return {}
    q = db.query(Shift).filter(Shift.chore_id.in_(chore_ids), Shift.on_date <= end)
    if exclude_shift_id is not None:
        q = q.filter(Shift.id != exclude_shift_id)
    return {Occurrence(s.chore_id, s.on_date, s.slot_index): s.volunteer_id for s in q.all()}


def _fold_range(
    db: Session,
    roster: Roster,
    chores: list[Chore],
    end: date,
    *,
    exclude_shift_id: str | None = None,
    state: RotationState | None = None,
):
    """Fold the whole roster from ``starts_on`` through ``end``: enumerate
    the pattern, replay every materialised row, assign the rest."""
    occ = occurrences_between(
        _chore_specs(chores),
        period_weeks=roster.period_weeks,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        start=roster.starts_on,
        end=end,
    )
    exclude_key = None
    if exclude_shift_id is not None:
        row = db.query(Shift).filter(Shift.id == exclude_shift_id).first()
        if row is not None:
            exclude_key = Occurrence(row.chore_id, row.on_date, row.slot_index)
    return fold(
        [o for o in occ if o != exclude_key],
        _fixed_rows(db, [c.id for c in chores], end, exclude_shift_id=exclude_shift_id),
        _eligible_by_chore(db, [c.id for c in chores]),
        ledger_weights(db, roster.id),
        _unavailable(db, roster.id),
        state=state,
    )


def project_range(db: Session, roster: Roster, chores: list[Chore], start: date, end: date):
    """The assignments for one roster over ``[start, end]`` — the shared
    oracle behind both the tick's pin step and the read-side outlook, so
    confirmed and outlook never disagree. The fold runs from the roster's
    start (history must advance the clocks); only ``[start, end]`` is
    returned."""
    return [pa for pa in _fold_range(db, roster, chores, end) if pa.occurrence.on_date >= start]


def _pin_window(db: Session, roster: Roster, chores: list[Chore], today: date) -> int:
    """Pin the incoming edge + prune stale window pins. Returns inserted."""
    chore_ids = [c.id for c in chores]
    end = horizon_end(roster, today)
    projected = project_range(db, roster, chores, today, end)
    existing, row_by_key = _window_pins(db, roster.id, chore_ids, today, end)
    diff = reconcile(existing, projected, today=today)
    return _apply(db, roster.id, diff, row_by_key)


def _reconcile_past(db: Session, roster_id: str, chore_ids: list[str], today: date) -> None:
    """Past scheduled shifts never completed → missed, one `missed` event
    per assignee (per-row, not a bulk UPDATE)."""
    if not chore_ids:
        return
    stale = (
        db.query(Shift).filter(Shift.chore_id.in_(chore_ids), Shift.on_date < today, Shift.status == "scheduled").all()
    )
    for shift in stale:
        shift.status = "missed"
        if shift.volunteer_id is not None:
            record_event(db, roster_id=roster_id, volunteer_id=shift.volunteer_id, kind="missed", shift_id=shift.id)


def _tick_roster(db: Session, roster: Roster, today: date) -> int:
    """Pin + prune + reconcile one roster. No-op while forming. No commit."""
    if roster.activated_at is None:
        return 0
    chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
    inserted = _pin_window(db, roster, chores, today)
    _reconcile_past(db, roster.id, [c.id for c in chores], today)
    return inserted


def pin_roster(db: Session, roster: Roster, today: date) -> int:
    """Pin a single roster's window now (used on activation), then commit."""
    inserted = _tick_roster(db, roster, today)
    db.commit()
    return inserted


def rebalance_core(db: Session, roster: Roster, today: date) -> int:
    """The rebalance mutation without the commit: drop every un-acted,
    un-reminded pin in the window (even ones still projected) so newly-
    enrolled volunteers fold in, then re-pin from the fresh projection.
    Reminded / acted pins are kept. No commit — the caller commits (real
    run) or rolls it back inside a SAVEPOINT (the dry-run calendar preview)."""
    if roster.activated_at is None:
        return 0
    chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
    end = horizon_end(roster, today)
    existing, row_by_key = _window_pins(db, roster.id, [c.id for c in chores], today, end)
    for pin in existing:
        if not pin.acted and not pin.reminded:
            db.delete(row_by_key[pin.key])
    db.flush()
    return _tick_roster(db, roster, today)


def rebalance_roster(db: Session, roster: Roster, today: date) -> int:
    """Re-pin the current window from the fresh projection, folding newly-
    enrolled volunteers into the confirmed window now. Changes confirmed
    assignments — an explicit, organiser-invoked action. Commits."""
    inserted = rebalance_core(db, roster, today)
    db.commit()
    return inserted


def run_tick(db: Session, today: date) -> tuple[int, int]:
    """Pin + prune + reconcile every live, running roster. Returns
    ``(rosters_processed, shifts_created)``."""
    rosters = db.query(Roster).filter(Roster.archived_at.is_(None)).all()
    created = 0
    for roster in rosters:
        # The sweep crosses every organisation, so each roster's own
        # tenant is bound for the shifts and events it creates.
        with tenancy.use(roster.tenant_id, roster.tenant.slug):
            created += _tick_roster(db, roster, today)
    db.commit()
    return len(rosters), created
