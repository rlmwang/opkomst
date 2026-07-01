"""Shift pinning + reconciliation — the daily ``roster-tick`` (design §7).

Occurrences are a deterministic projection of the pattern; ``Shift`` rows
are a sparse overlay materialised only inside the commit horizon. Per
**running** roster, ``run_tick``:

1. **pins the incoming edge** — for each occurrence in
   ``[today, today+commit_horizon_days]`` with no row yet, insert a pinned
   Shift (assigned via WRH, or ``open`` if nobody eligible);
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

from ..models import Chore, Enrollment, Roster, Shift, ShiftEvent
from .chore_assignment import assign_occurrence, net_credit, weight_from_ledger
from .chore_projection import ChoreSpec, Diff, Occurrence, PinnedShift, occurrences_between, project, reconcile


def record_event(db: Session, *, roster_id: str, volunteer_id: str, kind: str, shift_id: str | None = None) -> None:
    """Append one accountability event. The single write-point for the
    ShiftEvent log, used by the tick and the public shift-action routes."""
    db.add(ShiftEvent(roster_id=roster_id, volunteer_id=volunteer_id, kind=kind, shift_id=shift_id))


def ledger_weights(db: Session, roster_id: str) -> dict[str, float]:
    """Resolve the favour ledger for a roster into WRH weights. Thin impure
    wrapper: query the ``ShiftEvent`` rows, hand them to the pure
    ``net_credit`` fold, map each through ``weight_from_ledger``. Volunteers
    with no events are absent and default to weight 1.0 at lookup time."""
    rows = db.query(ShiftEvent.kind, ShiftEvent.volunteer_id).filter(ShiftEvent.roster_id == roster_id).all()
    credit = net_credit((kind, vid) for kind, vid in rows)
    return {vid: weight_from_ledger(c) for vid, c in credit.items()}


def _occupants(db: Session, chore_id: str, on_date: date, *, exclude_shift_id: str | None = None) -> set[str]:
    """Volunteers already scheduled on other slots of one occurrence — so
    we never double-book someone across two slots of the same shift."""
    q = db.query(Shift.volunteer_id).filter(
        Shift.chore_id == chore_id,
        Shift.on_date == on_date,
        Shift.status == "scheduled",
        Shift.volunteer_id.is_not(None),
    )
    if exclude_shift_id is not None:
        q = q.filter(Shift.id != exclude_shift_id)
    return {row[0] for row in q.all()}


def reassign_shift(db: Session, shift: Shift, *, exclude: set[str] | None = None) -> str | None:
    """Assign a single ``open`` shift (used by handoff). Picks the highest
    WRH-ranked eligible volunteer who is not excluded and not already on
    this occurrence. Returns the chosen volunteer id or ``None``. Does not
    commit."""
    chore = db.query(Chore).filter(Chore.id == shift.chore_id).first()
    if chore is None:
        return None
    eligible = [row[0] for row in db.query(Enrollment.volunteer_id).filter(Enrollment.chore_id == shift.chore_id).all()]
    if not eligible:
        return None
    skip = set(exclude or set()) | _occupants(db, shift.chore_id, shift.on_date, exclude_shift_id=shift.id)
    weights = ledger_weights(db, chore.roster_id)
    ranked = assign_occurrence(eligible, weights, chore_id=shift.chore_id, on_date=shift.on_date, count=len(eligible))
    chosen = next((v for v in ranked if v not in skip), None)
    if chosen is not None:
        shift.volunteer_id = chosen
        shift.status = "scheduled"
        record_event(db, roster_id=chore.roster_id, volunteer_id=chosen, kind="assigned", shift_id=shift.id)
    return chosen


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


def _horizon_end(roster: Roster, today: date) -> date:
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


def project_range(db: Session, roster: Roster, chores: list[Chore], start: date, end: date):
    """The projected assignments for one roster over ``[start, end]`` — the
    shared oracle behind both the tick's pin step and the read-side outlook,
    so confirmed and outlook never disagree."""
    occ = occurrences_between(
        _chore_specs(chores),
        period_weeks=roster.period_weeks,
        starts_on=roster.starts_on,
        ends_on=roster.ends_on,
        start=start,
        end=end,
    )
    return project(occ, _eligible_by_chore(db, [c.id for c in chores]), ledger_weights(db, roster.id))


def _pin_window(db: Session, roster: Roster, chores: list[Chore], today: date) -> int:
    """Pin the incoming edge + prune stale window pins. Returns inserted."""
    chore_ids = [c.id for c in chores]
    end = _horizon_end(roster, today)
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


def rebalance_roster(db: Session, roster: Roster, today: date) -> int:
    """Re-pin the current window from the fresh projection: drop every
    un-acted, un-reminded pin (even ones still projected) so newly-enrolled
    volunteers fold into the confirmed window now, then re-pin. Reminded /
    acted pins are kept. Changes confirmed assignments — an explicit,
    organiser-invoked action. Commits."""
    if roster.activated_at is None:
        return 0
    chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
    end = _horizon_end(roster, today)
    existing, row_by_key = _window_pins(db, roster.id, [c.id for c in chores], today, end)
    for pin in existing:
        if not pin.acted and not pin.reminded:
            db.delete(row_by_key[pin.key])
    db.flush()
    inserted = _tick_roster(db, roster, today)
    db.commit()
    return inserted


def run_tick(db: Session, today: date) -> tuple[int, int]:
    """Pin + prune + reconcile every live, running roster. Returns
    ``(rosters_processed, shifts_created)``."""
    rosters = db.query(Roster).filter(Roster.archived_at.is_(None)).all()
    created = 0
    for roster in rosters:
        created += _tick_roster(db, roster, today)
    db.commit()
    return len(rosters), created
