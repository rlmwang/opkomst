"""Occurrence materialisation for events, on the roster's recurrence rule.

An ``Event`` is a definition: shared content plus a recurrence rule that is
the chores roster's k-week cycle, reused. The pure date math lives in
``services/recurrence.py`` (``occurs_on`` / ``first_cycle_monday``); this
module enumerates the rule's dates and turns the ones inside the horizon
into ``Occurrence`` rows.

The rule:

- ``cycle_slots`` empty  -> a one-off: exactly one occurrence on
  ``starts_on`` at ``start_time``.
- ``cycle_slots`` non-empty -> recurring: every date ``d >= starts_on``
  where ``recurrence.occurs_on(d, ...)`` holds, bounded by the span
  (``span_weeks`` weeks from ``starts_on``; ``None`` = open-ended).

Each occurrence's concrete datetimes are the pattern date combined with the
event's shared ``start_time`` / ``end_time``. The "sessie i van N" ordinal
is not stored; it is the date rank (``session_index`` / ``total_sessions``).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..models import EmailDispatch, EmailStatus, Occurrence, Signup
from . import tenancy
from .recurrence import occurs_on
from .slug import new_slug


@dataclass(frozen=True, slots=True)
class OccurrenceSpec:
    """One dated instance the rule produces: its date rank and its
    materialised wall-clock datetimes. Pure — no row, no slug."""

    index: int
    starts_at: datetime
    ends_at: datetime


def _span_end(event) -> date | None:
    """The last calendar date the pattern may fall on, or ``None`` for an
    open-ended event. ``span_weeks`` weeks from ``starts_on`` inclusive."""
    if event.span_weeks is None:
        return None
    return event.starts_on + timedelta(days=event.span_weeks * 7 - 1)


def is_finite(event) -> bool:
    """Whether the event has a bounded, known session list. A one-off
    (``cycle_slots == []``) and any recurring event with a set ``span_weeks``
    are finite; only an open-ended recurring event (``span_weeks is None``)
    is not. A finite event materialises every session up front, ignoring the
    horizon, so "6 sessies" always resolves to six findable rows."""
    return not event.cycle_slots or event.span_weeks is not None


def _iter_dates(event) -> Iterator[date]:
    """Every date the rule produces, in ascending order. A one-off yields a
    single date (``starts_on``); a recurring event yields the cycle's dates,
    finite when ``span_weeks`` is set and an unbounded generator otherwise
    (callers break by date or count)."""
    if not event.cycle_slots:
        yield event.starts_on
        return
    span_end = _span_end(event)
    d = event.starts_on
    while span_end is None or d <= span_end:
        if occurs_on(d, cycle_slots=event.cycle_slots, period_weeks=event.period_weeks, starts_on=event.starts_on):
            yield d
        d += timedelta(days=1)


def occurrence_datetimes(event, on_date: date) -> tuple[datetime, datetime]:
    """The concrete wall-clock ``(starts_at, ends_at)`` for one pattern date:
    that date combined with the event's shared time of day."""
    return (
        datetime.combine(on_date, event.start_time),
        datetime.combine(on_date, event.end_time),
    )


def session_index(event, on_date: date) -> int:
    """The 0-based "sessie i" ordinal of an occurrence: how many of the
    rule's dates fall strictly before ``on_date``. Derived, never stored."""
    n = 0
    for d in _iter_dates(event):
        if d >= on_date:
            break
        n += 1
    return n


def total_sessions(event) -> int | None:
    """The "van N" total: the rule's finite session count, or ``None`` for an
    open-ended recurring event. A one-off is 1."""
    if event.cycle_slots and event.span_weeks is None:
        return None
    return sum(1 for _ in _iter_dates(event))


def _horizon_date(event, now: datetime) -> date:
    return (now + timedelta(days=event.horizon_days)).date()


def specs_to_materialise(event, now: datetime) -> list[OccurrenceSpec]:
    """Every date that should be a materialised row *now*.

    A **finite** event (``is_finite``) materialises its whole session list,
    ignoring the horizon, so a finite course is complete and findable the
    moment it is saved. An **open-ended** event materialises only the dates
    up to the horizon (``now + horizon_days``); the first occurrence is
    always included so even a far-future event has its first page, and the
    nightly tick pulls the rest across as the calendar advances."""
    finite = is_finite(event)
    horizon_end = _horizon_date(event, now)
    specs: list[OccurrenceSpec] = []
    first: date | None = None
    for index, d in enumerate(_iter_dates(event)):
        if first is None:
            first = d
        if not finite and d > horizon_end and d != first:
            break
        starts_at, ends_at = occurrence_datetimes(event, d)
        specs.append(OccurrenceSpec(index=index, starts_at=starts_at, ends_at=ends_at))
    return specs


def projected_future_specs(event, now: datetime, *, limit: int = 12) -> list[OccurrenceSpec]:
    """Beyond-horizon future dates, for the public page's read-only "upcoming
    dates" context (not yet sign-up-able because their row doesn't exist
    yet). Only open-ended events have these: a finite event materialises its
    whole span, so there is nothing beyond the horizon and this is empty."""
    if is_finite(event):
        return []
    horizon_end = _horizon_date(event, now)
    out: list[OccurrenceSpec] = []
    for index, d in enumerate(_iter_dates(event)):
        if d <= horizon_end:
            continue
        starts_at, ends_at = occurrence_datetimes(event, d)
        out.append(OccurrenceSpec(index=index, starts_at=starts_at, ends_at=ends_at))
        if len(out) >= limit:
            break
    return out


def _existing_dates(db: Session, event_id: str) -> dict[datetime, Occurrence]:
    rows = db.query(Occurrence).filter(Occurrence.event_id == event_id).all()
    return {o.starts_at: o for o in rows}


def materialise(db: Session, event, now: datetime, *, include_past: bool = False) -> list[Occurrence]:
    """Insert an ``Occurrence`` for every materialisable date of ``event``
    that doesn't exist yet. Never touches an existing row (frozen). Flushes so
    the new rows have ids; does not commit. Returns the rows created.

    A **recurring** event never fabricates a past-dated occurrence: its
    history is immutable, so only future dates are created (a past occurrence
    exists only because it was once future). A **one-off** is the event
    itself and its single date is created wherever it sits, past or future.
    ``include_past=True`` overrides the skip so the seed can back-fill a
    running course's past sessions for the local demo."""
    keep_past = include_past or not event.cycle_slots  # one-off: the single date is created anywhere
    existing = _existing_dates(db, event.id)
    created: list[Occurrence] = []
    for spec in specs_to_materialise(event, now):
        if not keep_past and spec.starts_at <= now:
            continue  # history is immutable: never fabricate a past session
        if spec.starts_at in existing:
            continue
        occ = Occurrence(
            event_id=event.id,
            slug=new_slug(),
            starts_at=spec.starts_at,
            ends_at=spec.ends_at,
        )
        db.add(occ)
        created.append(occ)
    if created:
        db.flush()
    return created


def _has_signups(db: Session, occurrence_id: str) -> bool:
    return db.query(Signup.id).filter(Signup.occurrence_id == occurrence_id).first() is not None


def _move_signups_and_dispatches(db: Session, src: Occurrence, dst: Occurrence) -> None:
    """Migrate ``src``'s sign-ups and pending dispatches onto ``dst`` (a
    removed session's attendees following it to a replacement). A registration
    already on ``dst`` collapses to a single line item; pending dispatches
    re-aim so the reminder/feedback fires for the new date."""
    dst_regs = {r for (r,) in db.query(Signup.registration_id).filter(Signup.occurrence_id == dst.id).all()}
    for su in db.query(Signup).filter(Signup.occurrence_id == src.id).all():
        if su.registration_id in dst_regs:
            db.delete(su)  # dedupe: this booking is already on the target
        else:
            su.occurrence_id = dst.id
            dst_regs.add(su.registration_id)
    for disp in db.query(EmailDispatch).filter(
        EmailDispatch.occurrence_id == src.id, EmailDispatch.status == EmailStatus.PENDING
    ):
        disp.occurrence_id = dst.id
    db.flush()


def _reconcile_one_off(db: Session, event, now: datetime) -> None:
    """A one-off has a single occurrence (the event itself). Re-point it to
    the chosen date wherever it sits, past or future, carrying its sign-ups
    and dispatches; collapse away any extras."""
    target_start, target_end = occurrence_datetimes(event, event.starts_on)
    occs = db.query(Occurrence).filter(Occurrence.event_id == event.id).all()
    if not occs:
        materialise(db, event, now, include_past=True)
        return
    keeper = next((o for o in occs if o.starts_at == target_start), None)
    if keeper is None:
        keeper = min(occs, key=lambda o: o.starts_at)
        keeper.starts_at, keeper.ends_at = target_start, target_end
    for o in occs:
        if o is not keeper:
            db.delete(o)  # collapsing several sessions to one: the rest are lost
    db.flush()


def reconcile(db: Session, event, now: datetime) -> None:
    """Reconcile occurrences + their sign-ups onto the edited schedule.

    A **one-off** re-points its single occurrence anywhere (see
    ``_reconcile_one_off``). A **recurring** event freezes the past entirely
    and reconciles only future occurrences: a uniform shift re-points every
    future date by a constant Δ; otherwise surviving dates are kept (times
    re-pointed), added dates materialised, and removed dates' sign-ups
    migrated to the nearest new session in the gap between their surviving
    neighbours (or lost if there is none). No occurrence ever survives
    off-pattern. Does not commit."""
    if not event.cycle_slots:
        _reconcile_one_off(db, event, now)
        return

    future_occs = sorted(
        (o for o in db.query(Occurrence).filter(Occurrence.event_id == event.id).all() if o.starts_at > now),
        key=lambda o: o.starts_at,
    )
    old_dates = [o.starts_at.date() for o in future_occs]
    new_specs = [s for s in specs_to_materialise(event, now) if s.starts_at > now]
    new_dt = {s.starts_at.date(): (s.starts_at, s.ends_at) for s in new_specs}
    new_dates = sorted(new_dt)

    # 1. Uniform shift: the whole future schedule slid by one constant Δ.
    if old_dates and len(old_dates) == len(new_dates):
        deltas = {(nd - od).days for od, nd in zip(old_dates, new_dates, strict=True)}
        if len(deltas) == 1 and (delta := deltas.pop()) != 0:
            # Re-point in a collision-free order (largest first when moving
            # later, smallest first when moving earlier).
            for occ in sorted(future_occs, key=lambda o: o.starts_at, reverse=delta > 0):
                nd = occ.starts_at.date() + timedelta(days=delta)
                ns, ne = occurrence_datetimes(event, nd)
                if ns <= now:
                    db.delete(occ)  # pushed into the past: it can't occur, dispatches cascade
                else:
                    occ.starts_at, occ.ends_at = ns, ne
                db.flush()
            materialise(db, event, now)
            return

    # 2. Structural change.
    new_set = set(new_dates)
    old_set = set(old_dates)
    surviving = [o for o in future_occs if o.starts_at.date() in new_set]
    removed = [o for o in future_occs if o.starts_at.date() not in new_set]
    added_dates = [d for d in new_dates if d not in old_set]

    for o in surviving:
        o.starts_at, o.ends_at = new_dt[o.starts_at.date()]
    db.flush()

    # Materialise the added dates so migration targets exist.
    materialise(db, event, now)
    added_occ = {
        o.starts_at.date(): o
        for o in db.query(Occurrence).filter(Occurrence.event_id == event.id)
        if o.starts_at.date() in set(added_dates)
    }
    surviving_dates = sorted(o.starts_at.date() for o in surviving)

    for o in removed:
        d_r = o.starts_at.date()
        left = max((d for d in surviving_dates if d < d_r), default=None)
        right = min((d for d in surviving_dates if d > d_r), default=None)
        candidates = [d for d in added_dates if (left is None or d > left) and (right is None or d < right)]
        if candidates and _has_signups(db, o.id):
            target_date = min(candidates, key=lambda d: (abs((d - d_r).days), d))
            _move_signups_and_dispatches(db, o, added_occ[target_date])
        db.delete(o)  # off-pattern occurrence removed; unmigrated sign-ups/dispatches cascade
    db.flush()


def run_tick(db: Session, now: datetime) -> tuple[int, int]:
    """Materialise the incoming horizon edge for every live (non-archived)
    event. Mirrors the roster tick: pure enumeration + insert-missing, no
    touch of existing rows. Returns ``(events_processed, occurrences_created)``."""
    from ..models import Event

    events = db.query(Event).filter(Event.archived_at.is_(None)).all()
    created = 0
    for event in events:
        # The sweep crosses every organisation, so each event's own
        # tenant is bound for the rows it is about to create.
        with tenancy.use(event.tenant_id, event.tenant.brand_slug):
            created += len(materialise(db, event, now))
    db.commit()
    return len(events), created
