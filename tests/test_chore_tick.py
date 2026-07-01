"""Shift generation + assignment + reconcile — ``services/chore_tick``.

Dates are anchored to Monday 2026-01-05 so the recurrence math is
predictable. Horizon is 28 days → window is 2026-01-05 … 2026-02-02.
"""

from datetime import UTC, date, datetime

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, User, Volunteer
from backend.services import chore_tick

TODAY = date(2026, 1, 5)  # a Monday
# Wednesdays in [TODAY, TODAY+28]: Jan 7, 14, 21, 28.
WEEKLY_WED = [date(2026, 1, 7), date(2026, 1, 14), date(2026, 1, 21), date(2026, 1, 28)]


def _roster(db, *, period_weeks=1, anchor=None, ends_on=None, cycle_slots=(2,), people=1):
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug=f"r{period_weeks}{'x' if anchor else ''}",
        name="R",
        created_by=user.id,
        chapter_id=chapter.id,
        starts_on=TODAY,
        period_weeks=period_weeks,
        anchor_monday=anchor,
        ends_on=ends_on,
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


def test_tick_is_idempotent(db):
    _, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    n1 = db.query(Shift).filter(Shift.chore_id == chore.id).count()
    _, created2 = chore_tick.run_tick(db, TODAY)
    n2 = db.query(Shift).filter(Shift.chore_id == chore.id).count()
    assert n1 == n2 == 4
    assert created2 == 0


def test_biweekly_hits_alternating_weeks(db):
    # cycle_slots=[2] with k=2 anchored on TODAY → only week-A Wednesdays.
    _, chore = _roster(db, period_weeks=2, anchor=TODAY, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == [date(2026, 1, 7), date(2026, 1, 21)]


def test_ends_on_caps_the_horizon(db):
    _, chore = _roster(db, cycle_slots=(2,), ends_on=date(2026, 1, 10))
    chore_tick.run_tick(db, TODAY)
    assert _shift_dates(db, chore.id) == [date(2026, 1, 7)]


def test_people_per_shift_materialises_multiple_slots(db):
    _, chore = _roster(db, cycle_slots=(2,), people=2)
    chore_tick.run_tick(db, TODAY)
    # 4 Wednesdays × 2 people = 8 shift rows, slot_index 0 and 1 per date.
    shifts = db.query(Shift).filter(Shift.chore_id == chore.id).all()
    assert len(shifts) == 8
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
    assert len(scheduled) == 4  # all four Wednesdays assigned to the sole volunteer
    assert all(s.volunteer_id == vol.id for s in scheduled)


def test_no_eligible_volunteer_leaves_shifts_open(db):
    _, chore = _roster(db, cycle_slots=(2,))
    chore_tick.run_tick(db, TODAY)
    assert all(s.status == "open" for s in db.query(Shift).filter(Shift.chore_id == chore.id).all())


def test_reconcile_past_scheduled_to_missed(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    vol = Volunteer(roster_id=roster.id, display_name="V", edit_token_hash="h2")
    db.add(vol)
    db.commit()
    # A past, still-scheduled shift (before TODAY).
    db.add(
        Shift(chore_id=chore.id, on_date=date(2025, 12, 31), slot_index=0, status="scheduled", volunteer_id=vol.id)
    )
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
    assert past.status == "done"  # completed shifts are left alone


def test_leave_reopens_and_reassigns_on_next_tick(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    a = Volunteer(roster_id=roster.id, display_name="A", edit_token_hash="ha")
    b = Volunteer(roster_id=roster.id, display_name="B", edit_token_hash="hb")
    db.add_all([a, b])
    db.commit()
    db.add_all([Enrollment(volunteer_id=a.id, chore_id=chore.id), Enrollment(volunteer_id=b.id, chore_id=chore.id)])
    db.commit()
    chore_tick.run_tick(db, TODAY)
    assert db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").count() == 4

    # A leaves → their future shifts SET NULL (status still scheduled).
    db.delete(a)
    db.commit()
    orphaned = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.volunteer_id.is_(None)).count()
    assert orphaned > 0

    # Next tick reopens + reassigns the orphaned shifts to B.
    chore_tick.run_tick(db, TODAY)
    assert db.query(Shift).filter(Shift.chore_id == chore.id, Shift.volunteer_id.is_(None)).count() == 0
    assert db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").count() == 4
