"""Shift pinning + prune + reconcile — ``services/chore_tick`` (task 11).

Dates are anchored to Monday 2026-01-05. The helper rosters use a 28-day
commit horizon so the window is 2026-01-05 … 2026-02-02, and are created
already ``running`` (activated) unless a test opts out.
"""

from datetime import UTC, date, datetime

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, User, Volunteer
from backend.services import chore_tick

TODAY = date(2026, 1, 5)  # a Monday
# Wednesdays in [TODAY, TODAY+28]: Jan 7, 14, 21, 28.
WEEKLY_WED = [date(2026, 1, 7), date(2026, 1, 14), date(2026, 1, 21), date(2026, 1, 28)]


def _roster(db, *, period_weeks=1, ends_on=None, cycle_slots=(2,), people=1, activate=True):
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug=f"r{period_weeks}",
        name="R",
        created_by=user.id,
        chapter_id=chapter.id,
        starts_on=TODAY,
        period_weeks=period_weeks,
        ends_on=ends_on,
        commit_horizon_days=28,
        activated_at=datetime.now(UTC) if activate else None,
    )
    db.add(roster)
    db.commit()
    chore = Chore(roster_id=roster.id, name="Bins", ordinal=1, cycle_slots=list(cycle_slots), people_per_shift=people)
    db.add(chore)
    db.commit()
    return roster, chore


def _shift_dates(db, chore_id) -> list[date]:
    return [s.on_date for s in db.query(Shift).filter(Shift.chore_id == chore_id).order_by(Shift.on_date).all()]


def test_weekly_materialises_the_right_dates(db):
    _, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == WEEKLY_WED


def test_forming_roster_pins_nothing(db):
    _, chore = _roster(db, cycle_slots=(2,), activate=False)
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == []


def test_tick_is_idempotent(db):
    _, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    n1 = db.query(Shift).filter(Shift.chore_id == chore.id).count()
    _, created2 = chore_tick.run_tick(db, TODAY)
    n2 = db.query(Shift).filter(Shift.chore_id == chore.id).count()
    assert n1 == n2 == 4
    assert created2 == 0


def test_biweekly_hits_alternating_weeks(db):
    _, chore = _roster(db, period_weeks=2, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == [date(2026, 1, 7), date(2026, 1, 21)]


def test_ends_on_caps_the_horizon(db):
    _, chore = _roster(db, cycle_slots=(2,), ends_on=date(2026, 1, 10))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == [date(2026, 1, 7)]


def test_people_per_shift_materialises_multiple_slots(db):
    _, chore = _roster(db, cycle_slots=(2,), people=2)
    chore_tick.run_tick(db, TODAY)
    shifts = db.query(Shift).filter(Shift.chore_id == chore.id).all()
    assert len(shifts) == 8  # 4 Wednesdays × 2 people
    assert {s.slot_index for s in shifts} == {0, 1}


def test_enrolled_volunteer_gets_assigned(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="h1")
    db.add(vol)
    db.commit()
    db.add(Enrollment(volunteer_id=vol.id, chore_id=chore.id))
    db.commit()
    chore_tick.run_tick(db, TODAY)
    scheduled = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").all()
    assert len(scheduled) == 4
    assert all(s.volunteer_id == vol.id for s in scheduled)


def test_no_eligible_volunteer_leaves_shifts_open(db):
    _, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert all(s.status == "open" for s in db.query(Shift).filter(Shift.chore_id == chore.id).all())


def test_edit_prunes_orphaned_unacted_pins(db):
    # Pin Wednesday shifts, then move the chore to Thursday. The now-orphan,
    # un-acted Wednesday pins are pruned; Thursday pins take their place.
    roster, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == WEEKLY_WED
    chore.cycle_slots = [3]  # Thursday
    db.commit()
    chore_tick.run_tick(db, TODAY)
    thursdays = [date(2026, 1, 8), date(2026, 1, 15), date(2026, 1, 22), date(2026, 1, 29)]
    assert _shift_dates(db, chore.id) == thursdays


def test_edit_keeps_reminded_pin_even_when_orphaned(db):
    # A reminded pin is a commitment: an edit that orphans it must not prune it.
    roster, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    wed = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == date(2026, 1, 7)).one()
    wed.reminder_sent_at = datetime.now(UTC)
    chore.cycle_slots = [3]  # move to Thursday, orphaning every Wednesday
    db.commit()
    chore_tick.run_tick(db, TODAY)
    kept = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == date(2026, 1, 7)).one_or_none()
    assert kept is not None  # reminded pin survives the edit


def test_reconcile_past_scheduled_to_missed(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="h2")
    db.add(vol)
    db.commit()
    db.add(Shift(chore_id=chore.id, on_date=date(2025, 12, 31), slot_index=0, status="scheduled", volunteer_id=vol.id))
    db.commit()
    chore_tick.run_tick(db, TODAY)
    past = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == date(2025, 12, 31)).one()
    assert past.status == "missed"


def test_done_past_shift_is_not_reconciled(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="h3")
    db.add(vol)
    db.commit()
    db.add(
        Shift(
            chore_id=chore.id,
            on_date=date(2025, 12, 31),
            slot_index=0,
            status="done",
            volunteer_id=vol.id,
            done_at=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    db.commit()
    chore_tick.run_tick(db, TODAY)
    past = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == date(2025, 12, 31)).one()
    assert past.status == "done"


def test_rebalance_folds_in_a_late_volunteer(db):
    # Activate with no volunteers → all open. A volunteer enrols, then a
    # rebalance re-pins the window and assigns them.
    roster, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert all(s.status == "open" for s in db.query(Shift).filter(Shift.chore_id == chore.id).all())
    vol = Volunteer(roster_id=roster.id, display_name="Late", edit_token_hash="hl")
    db.add(vol)
    db.commit()
    db.add(Enrollment(volunteer_id=vol.id, chore_id=chore.id))
    db.commit()
    chore_tick.rebalance_roster(db, roster, TODAY)
    scheduled = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").all()
    assert len(scheduled) == 4
    assert all(s.volunteer_id == vol.id for s in scheduled)


def test_rebalance_preview_is_a_dry_run(db):
    # Same setup: activate with no volunteers (all open), then enrol one.
    roster, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    vol = Volunteer(roster_id=roster.id, display_name="Late", edit_token_hash="hp")
    db.add(vol)
    db.commit()
    db.add(Enrollment(volunteer_id=vol.id, chore_id=chore.id))
    db.commit()

    # The dry-run runs the core inside a SAVEPOINT: it would assign every
    # open shift to the newcomer, but rolling back leaves the pins untouched
    # (this is exactly what the calendar preview relies on).
    savepoint = db.begin_nested()
    chore_tick.rebalance_core(db, roster, TODAY)
    db.flush()
    scheduled = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").all()
    assert len(scheduled) == 4
    assert all(s.volunteer_id == vol.id for s in scheduled)
    savepoint.rollback()
    assert all(s.status == "open" for s in db.query(Shift).filter(Shift.chore_id == chore.id).all())
