"""Shift materialisation + fair assignment — the daily ``roster-tick``.

``run_tick`` walks every live roster and, per roster:

1. **extends** the shift horizon — for each chore, insert ``open`` Shift
   rows (one per ``people_per_shift``) for every in-window date the
   recurrence lands on that has no shift yet;
2. **assigns** every ``open`` shift in the horizon to an eligible
   volunteer via the fairness policy (loads accrue within the batch so
   the distribution stays balanced);
3. **reconciles** the past — ``scheduled`` shifts before today that were
   never marked done flip to ``missed``.

``reassign_shift`` is the single-shift variant used by the handoff
endpoint. All assignment goes through the pure
``chore_assignment.assign_occurrence`` (weighted rendezvous hashing); the
only impure step is ``ledger_weights``, which folds the ``ShiftEvent`` log
into WRH weights.
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Chore, Enrollment, Roster, Shift, ShiftEvent
from .chore_assignment import assign_occurrence, net_credit, weight_from_ledger
from .recurrence import occurs_on


def record_event(db: Session, *, roster_id: str, volunteer_id: str, kind: str, shift_id: str | None = None) -> None:
    """Append one accountability event. The single write-point for the
    ShiftEvent log, used by the tick and the public shift-action routes."""
    db.add(ShiftEvent(roster_id=roster_id, volunteer_id=volunteer_id, kind=kind, shift_id=shift_id))


# How far ahead shifts are materialised + assigned. A daily tick keeps a
# rolling four-week window filled. Module constant (not env): there's no
# operational reason to tune it per-deploy.
HORIZON_DAYS = 28


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


def _extend(db: Session, roster: Roster, chores: list[Chore], start: date, end: date) -> int:
    created = 0
    for chore in chores:
        existing = {
            (row[0], row[1])
            for row in db.query(Shift.on_date, Shift.slot_index)
            .filter(Shift.chore_id == chore.id, Shift.on_date >= start, Shift.on_date <= end)
            .all()
        }
        d = start
        while d <= end:
            if occurs_on(
                d,
                cycle_slots=chore.cycle_slots,
                period_weeks=roster.period_weeks,
                starts_on=roster.starts_on,
            ):
                for slot in range(chore.people_per_shift):
                    if (d, slot) not in existing:
                        db.add(Shift(chore_id=chore.id, on_date=d, slot_index=slot, status="open"))
                        created += 1
            d += timedelta(days=1)
    db.flush()
    return created


def _assign(db: Session, roster_id: str, chore_ids: list[str], today: date, end: date) -> None:
    if not chore_ids:
        return
    eligible_by_chore: dict[str, list[str]] = {}
    for cid, vid in (
        db.query(Enrollment.chore_id, Enrollment.volunteer_id).filter(Enrollment.chore_id.in_(chore_ids)).all()
    ):
        eligible_by_chore.setdefault(cid, []).append(vid)

    weights = ledger_weights(db, roster_id)

    # Volunteers already scheduled per occurrence (chore, date) — a shift's
    # other slots — so nobody is double-booked on the same occurrence.
    occupied: dict[tuple[str, date], set[str]] = {}
    for cid, on_date, vid in (
        db.query(Shift.chore_id, Shift.on_date, Shift.volunteer_id)
        .filter(
            Shift.chore_id.in_(chore_ids),
            Shift.status == "scheduled",
            Shift.volunteer_id.is_not(None),
            Shift.on_date >= today,
            Shift.on_date <= end,
        )
        .all()
    ):
        occupied.setdefault((cid, on_date), set()).add(vid)

    open_shifts = (
        db.query(Shift)
        .filter(
            Shift.chore_id.in_(chore_ids),
            Shift.status == "open",
            Shift.on_date >= today,
            Shift.on_date <= end,
        )
        .order_by(Shift.chore_id, Shift.on_date, Shift.slot_index)
        .all()
    )
    # Group open slots by occurrence; fill each with the top WRH-ranked
    # eligible volunteers not already on that occurrence.
    groups: dict[tuple[str, date], list[Shift]] = {}
    for shift in open_shifts:
        groups.setdefault((shift.chore_id, shift.on_date), []).append(shift)

    for (cid, on_date), shifts in groups.items():
        eligible = eligible_by_chore.get(cid, [])
        if not eligible:
            continue
        ranked = assign_occurrence(eligible, weights, chore_id=cid, on_date=on_date, count=len(eligible))
        taken = occupied.setdefault((cid, on_date), set())
        candidates = (v for v in ranked if v not in taken)
        for shift in shifts:
            chosen = next(candidates, None)
            if chosen is None:
                break
            shift.volunteer_id = chosen
            shift.status = "scheduled"
            record_event(db, roster_id=roster_id, volunteer_id=chosen, kind="assigned", shift_id=shift.id)
            taken.add(chosen)
    db.flush()


def run_tick(db: Session, today: date) -> tuple[int, int]:
    """Extend + assign + reconcile every live roster. Returns
    ``(rosters_processed, shifts_created)``."""
    rosters = db.query(Roster).filter(Roster.archived_at.is_(None)).all()
    created = 0
    for roster in rosters:
        chores = db.query(Chore).filter(Chore.roster_id == roster.id).all()
        chore_ids = [c.id for c in chores]
        end = today + timedelta(days=HORIZON_DAYS)
        if roster.ends_on is not None and roster.ends_on < end:
            end = roster.ends_on
        start = max(today, roster.starts_on)
        if start <= end:
            created += _extend(db, roster, chores, start, end)
            # A volunteer leaving SET-NULLs their future shifts but leaves
            # the status 'scheduled' — reopen those so _assign fills them.
            if chore_ids:
                db.query(Shift).filter(
                    Shift.chore_id.in_(chore_ids),
                    Shift.on_date >= today,
                    Shift.status == "scheduled",
                    Shift.volunteer_id.is_(None),
                ).update(
                    # Clear the reminder stamp too: the new assignee gets
                    # their own reminder, not suppressed by the leaver's.
                    {Shift.status: "open", Shift.reminder_sent_at: None},
                    synchronize_session=False,
                )
                db.flush()
            _assign(db, roster.id, chore_ids, today, end)
        # Reconcile: past scheduled shifts never completed → missed. Done
        # per-row (not a bulk UPDATE) so each gets a `missed` event for
        # its assignee.
        if chore_ids:
            stale = (
                db.query(Shift)
                .filter(
                    Shift.chore_id.in_(chore_ids),
                    Shift.on_date < today,
                    Shift.status == "scheduled",
                )
                .all()
            )
            for shift in stale:
                shift.status = "missed"
                if shift.volunteer_id is not None:
                    record_event(
                        db, roster_id=roster.id, volunteer_id=shift.volunteer_id, kind="missed", shift_id=shift.id
                    )
    db.commit()
    return len(rosters), created
