"""Occurrence materialisation + reconcile — the recurring-events engine, on
the roster's k-week cycle rule.

The date math is the shared pure ``recurrence.occurs_on`` (unit-tested for
chores); here we test the event layer: enumeration bounded by span + horizon,
the one-off case, the derived session ordinals, and materialise/reconcile
against the DB.
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from _helpers.events import first_occurrence, make_event, weekly_slots
from _helpers.signups import make_signup

from backend.models import EmailChannel, EmailDispatch, EmailStatus, Occurrence, Signup
from backend.services import event_recurrence
from backend.services.events import now_wallclock


def _rule(starts_on, cycle_slots, *, period_weeks=1, span_weeks=None, horizon_days=90):
    """A DB-free stand-in carrying just the rule attributes the pure
    enumeration reads."""
    return SimpleNamespace(
        starts_on=starts_on,
        cycle_slots=cycle_slots,
        period_weeks=period_weeks,
        span_weeks=span_weeks,
        horizon_days=horizon_days,
        start_time=time(19, 0),
        end_time=time(21, 0),
    )


# --- pure enumeration -----------------------------------------------------


def test_one_off_yields_single_date_at_starts_on():
    e = _rule(date(2026, 8, 3), cycle_slots=[])
    assert event_recurrence.total_sessions(e) == 1
    assert event_recurrence.session_index(e, date(2026, 8, 3)) == 0


def test_weekly_span_counts_one_session_per_week():
    mon = date(2026, 8, 3)  # a Monday
    e = _rule(mon, cycle_slots=[mon.weekday()], span_weeks=6)
    assert event_recurrence.total_sessions(e) == 6  # 6 weekly sessions
    assert event_recurrence.session_index(e, mon) == 0
    assert event_recurrence.session_index(e, mon + timedelta(weeks=3)) == 3


def test_two_week_cycle_alternates_weekdays():
    mon = date(2026, 8, 3)  # Monday, weekday 0
    # Week A: Tuesday (offset 1); week B: Thursday (offset 1*7+3 = 10).
    e = _rule(mon, cycle_slots=[1, 10], period_weeks=2, span_weeks=4)
    # 4 weeks = 2 cycles → Tue, Thu, Tue, Thu = 4 sessions.
    assert event_recurrence.total_sessions(e) == 4
    tue_w0 = mon + timedelta(days=1)
    thu_w1 = mon + timedelta(days=10)
    assert event_recurrence.session_index(e, tue_w0) == 0
    assert event_recurrence.session_index(e, thu_w1) == 1


def test_open_ended_recurring_has_no_total():
    mon = date(2026, 8, 3)
    e = _rule(mon, cycle_slots=[mon.weekday()], span_weeks=None)
    assert event_recurrence.total_sessions(e) is None


# --- materialise ----------------------------------------------------------


def test_one_off_materialises_single_occurrence(db):
    event = make_event(db, cycle_slots=[])
    occs = db.query(Occurrence).filter(Occurrence.event_id == event.id).all()
    assert len(occs) == 1
    assert occs[0].starts_at == datetime.combine(event.starts_on, event.start_time)


def test_finite_materialises_all_sessions_ignoring_horizon(db):
    # Weekly, 6-week span, but only a 21-day horizon: a FINITE event
    # materialises every session anyway, so "6 sessies" = 6 findable rows.
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=6, horizon_days=21)
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == 6
    # Nothing sits beyond the horizon for a finite event.
    assert event_recurrence.projected_future_specs(event, now_wallclock()) == []
    assert event_recurrence.is_finite(event) is True


def test_open_ended_materialises_within_horizon_only(db):
    # Open-ended (span_weeks=None): only the in-horizon slice exists; the
    # rest are a projection the nightly tick will pull across later.
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(
        db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=None, horizon_days=21
    )
    dates = sorted(o.starts_at.date() for o in db.query(Occurrence).filter(Occurrence.event_id == event.id))
    assert dates == [start, start + timedelta(weeks=1), start + timedelta(weeks=2)]  # day 1, 8, 15 in horizon
    projected = event_recurrence.projected_future_specs(event, now_wallclock())
    assert [s.index for s in projected][:3] == [3, 4, 5]  # weeks beyond the horizon
    assert event_recurrence.is_finite(event) is False


def test_materialise_is_idempotent_and_freezes_existing(db):
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=3)
    before = {o.id: o.starts_at for o in db.query(Occurrence).filter(Occurrence.event_id == event.id)}
    event_recurrence.materialise(db, event, now_wallclock())
    after = {o.id: o.starts_at for o in db.query(Occurrence).filter(Occurrence.event_id == event.id)}
    assert before == after  # no new rows, same ids


def test_far_future_one_off_still_gets_its_first_page(db):
    # starts_on beyond the horizon: index 0 is always materialised so the
    # event has a public page immediately.
    event = make_event(db, starts_in=timedelta(days=400), horizon_days=90, cycle_slots=[])
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == 1


# --- reconcile ------------------------------------------------------------


def test_reconcile_prunes_empty_future_occurrences_on_shrink(db):
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=5)
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == 5
    event.span_weeks = 2  # weeks 2,3,4 (day 14,21,28) fall outside the new span
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    dates = sorted(o.starts_at.date() for o in db.query(Occurrence).filter(Occurrence.event_id == event.id))
    assert dates == [start, start + timedelta(weeks=1)]


def test_reconcile_loses_booked_removed_session_with_no_replacement(db):
    # Shrinking the span drops the tail sessions. A booked dropped session
    # with no new session in its gap is lost (no zombie left off-pattern).
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=5)
    booked_date = start + timedelta(weeks=4)
    occ4 = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(booked_date, event.start_time),
        )
        .one()
    )
    make_signup(db, event, occurrence=occ4, email=None)  # someone booked week 5
    event.span_weeks = 2
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    dates = sorted(o.starts_at.date() for o in db.query(Occurrence).filter(Occurrence.event_id == event.id))
    # Only the two in-span sessions remain; the booked week-4 session is gone.
    assert dates == [start, start + timedelta(weeks=1)]
    assert db.query(Signup).filter(Signup.occurrence_id == occ4.id).count() == 0


def test_reconcile_uniform_shift_moves_signups_with_the_schedule(db):
    # Sliding a finite weekly course by a whole week shifts every future
    # session by 7 days; each session's sign-ups follow it (session i -> i).
    start = now_wallclock().date() + timedelta(days=7)
    event = make_event(db, starts_in=timedelta(days=7), cycle_slots=weekly_slots(start), span_weeks=4)
    first = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(start, event.start_time),
        )
        .one()
    )
    make_signup(db, event, occurrence=first, email=None)  # booked the first session
    # Slide the whole course one week later (new weekday is the same).
    event.starts_on = start + timedelta(weeks=1)
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    # The booking's session moved to +1 week; the sign-up rode the row.
    moved = db.query(Occurrence).filter(Occurrence.id == first.id).one()
    assert moved.starts_at.date() == start + timedelta(weeks=1)
    assert db.query(Signup).filter(Signup.occurrence_id == first.id).count() == 1


def test_reconcile_migrates_signups_to_new_session_in_the_gap(db):
    # Move one of two weekdays (Mon+Wed -> Mon+Thu): the removed Wednesday's
    # sign-ups migrate to the new Thursday that sits between it and the
    # surviving Monday of the next week.
    # Anchor on a Monday so weekday offsets are stable.
    monday = now_wallclock().date() + timedelta(days=(7 - now_wallclock().date().weekday()) % 7 or 7)
    event = make_event(
        db,
        starts_on=monday,
        starts_in=timedelta(days=1),  # ignored (starts_on given)
        cycle_slots=[0, 2],  # Mon (0), Wed (2)
        period_weeks=1,
        span_weeks=3,
    )
    wed = monday + timedelta(days=2)
    occ_wed = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(wed, event.start_time),
        )
        .one()
    )
    make_signup(db, event, occurrence=occ_wed, email=None)
    event.cycle_slots = [0, 3]  # Mon, Thu — Wednesday removed, Thursday added
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    thu = monday + timedelta(days=3)
    occ_thu = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(thu, event.start_time),
        )
        .one()
    )
    # Wednesday is gone; its sign-up migrated onto the new Thursday.
    assert db.query(Occurrence).filter(Occurrence.id == occ_wed.id).first() is None
    assert db.query(Signup).filter(Signup.occurrence_id == occ_thu.id).count() == 1


def test_reconcile_migrates_pending_dispatch_with_signups(db):
    # A removed session's pending reminder/feedback dispatch follows its
    # sign-ups to the replacement session (dispatches key on the date).
    monday = now_wallclock().date() + timedelta(days=(7 - now_wallclock().date().weekday()) % 7 or 7)
    event = make_event(db, starts_on=monday, cycle_slots=[0, 2], period_weeks=1, span_weeks=3)
    wed = monday + timedelta(days=2)
    occ_wed = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(wed, event.start_time),
        )
        .one()
    )
    make_signup(db, event, occurrence=occ_wed, email=None)
    db.add(
        EmailDispatch(
            occurrence_id=occ_wed.id, channel=EmailChannel.FEEDBACK, status=EmailStatus.PENDING, encrypted_email=b"x"
        )
    )
    db.flush()
    event.cycle_slots = [0, 3]  # Wed -> Thu
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    thu = monday + timedelta(days=3)
    occ_thu = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(thu, event.start_time),
        )
        .one()
    )
    assert db.query(EmailDispatch).filter(EmailDispatch.occurrence_id == occ_thu.id).count() == 1
    assert db.query(EmailDispatch).filter(EmailDispatch.occurrence_id == occ_wed.id).count() == 0


def test_materialise_never_fabricates_past_for_recurring(db):
    # A recurring event whose start is behind now materialises only its
    # remaining future sessions; the past isn't back-filled.
    start = now_wallclock().date() - timedelta(days=16)  # ~2.3 weeks ago
    event = make_event(db, starts_on=start, cycle_slots=weekly_slots(start), span_weeks=6)
    # make_event uses include_past=True, so first re-materialise via the
    # production path (skip past) against a fresh event to observe the rule.
    other = make_event(db, starts_on=start, cycle_slots=weekly_slots(start), span_weeks=6, name="prod")
    for o in list(other.occurrences):
        db.delete(o)
    db.flush()
    event_recurrence.materialise(db, other, now_wallclock())  # production: skip past
    dates = sorted(o.starts_at.date() for o in db.query(Occurrence).filter(Occurrence.event_id == other.id))
    now_d = now_wallclock().date()
    assert dates and all(d > now_d for d in dates)  # only future sessions materialised
    # (the include_past fixture ``event`` does have the past ones, for contrast)
    assert any(o.starts_at.date() <= now_d for o in event.occurrences)


def test_reconcile_one_off_can_move_into_the_past(db):
    # A one-off's single session can be corrected into the past, carrying its
    # sign-up on the same row (the historical-mistake fix).
    event = make_event(db, starts_in=timedelta(days=3), cycle_slots=[])  # one-off, future
    occ = first_occurrence(event)
    make_signup(db, event, occurrence=occ, email=None)
    past = now_wallclock().date() - timedelta(days=5)
    event.starts_on = past
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    moved = db.query(Occurrence).filter(Occurrence.event_id == event.id).one()  # still exactly one
    assert moved.starts_at.date() == past
    assert db.query(Signup).filter(Signup.occurrence_id == moved.id).count() == 1


def test_reconcile_repoints_time_of_day_on_time_change(db):
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(
        db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=4, start_time=time(19, 0)
    )
    event.start_time = time(18, 0)
    event.end_time = time(20, 0)
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    future = db.query(Occurrence).filter(Occurrence.event_id == event.id, Occurrence.starts_at > now_wallclock()).all()
    assert future and all(o.starts_at.time() == time(18, 0) for o in future)  # re-pointed, dates unchanged


def test_reconcile_never_touches_past_occurrences(db):
    # First session already happened; shrinking span must not delete history.
    start = now_wallclock().date() - timedelta(days=3)
    event = make_event(db, starts_in=timedelta(days=-3), cycle_slots=weekly_slots(start), span_weeks=4)
    past = first_occurrence(event)
    past_id, past_start = past.id, past.starts_at
    event.span_weeks = 1
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    still = db.query(Occurrence).filter(Occurrence.id == past_id).one()
    assert still.starts_at == past_start  # frozen


def test_pruned_occurrence_cascades_its_dispatches(db):
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=3)
    last_date = start + timedelta(weeks=2)
    occ2 = (
        db.query(Occurrence)
        .filter(
            Occurrence.event_id == event.id,
            Occurrence.starts_at == datetime.combine(last_date, event.start_time),
        )
        .one()
    )
    db.add(
        EmailDispatch(
            occurrence_id=occ2.id,
            channel=EmailChannel.FEEDBACK,
            status=EmailStatus.PENDING,
            encrypted_email=b"x",
        )
    )
    db.flush()
    event.span_weeks = 2  # week 2 (occ2) drops out of the span
    db.flush()
    event_recurrence.reconcile(db, event, now_wallclock())
    db.flush()
    assert db.query(Occurrence).filter(Occurrence.id == occ2.id).first() is None
    assert db.query(EmailDispatch).filter(EmailDispatch.occurrence_id == occ2.id).count() == 0
    assert db.query(Signup).filter(Signup.occurrence_id == occ2.id).count() == 0


# --- run_tick (the sweep the CLI event-tick invokes) ----------------------


def test_run_tick_extends_open_ended_across_horizon(db):
    # Only an OPEN-ENDED event grows over time; the tick pulls the next
    # future date across the horizon as the calendar advances (a realistic
    # small step, so no session falls past unmaterialised).
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(
        db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=None, horizon_days=14
    )
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == 2  # weeks 0,1 in 14 days

    processed, created = event_recurrence.run_tick(db, now_wallclock() + timedelta(days=7))
    assert processed >= 1
    assert created == 1  # week 2 crossed the moved horizon, still in the future
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == 3

    _, again = event_recurrence.run_tick(db, now_wallclock() + timedelta(days=7))
    assert again == 0  # idempotent


def test_run_tick_skips_archived_events(db):
    start = now_wallclock().date() + timedelta(days=1)
    event = make_event(db, starts_in=timedelta(days=1), cycle_slots=weekly_slots(start), span_weeks=6, horizon_days=21)
    before = db.query(Occurrence).filter(Occurrence.event_id == event.id).count()
    event.archived_at = now_wallclock()
    db.flush()

    _, created = event_recurrence.run_tick(db, now_wallclock() + timedelta(days=40))
    assert created == 0
    assert db.query(Occurrence).filter(Occurrence.event_id == event.id).count() == before
