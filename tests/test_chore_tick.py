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


def _second_chore(db, roster, cycle_slots):
    other = Chore(roster_id=roster.id, name="Mop", ordinal=2, cycle_slots=list(cycle_slots), people_per_shift=1)
    db.add(other)
    db.commit()
    return other


def _volunteers_in(db, roster, chores, names):
    vols = [Volunteer(roster_id=roster.id, display_name=n, edit_token_hash=f"h{n}") for n in names]
    db.add_all(vols)
    db.commit()
    db.add_all(Enrollment(volunteer_id=v.id, chore_id=c.id) for v in vols for c in chores)
    db.commit()
    return vols


def test_two_chores_on_one_day_get_distinct_assignees(db):
    # Wed + Fri, two chores, two volunteers in both: every date must split
    # the pair, never stack both chores on one volunteer.
    roster, chore = _roster(db, cycle_slots=(2, 4))
    other = _second_chore(db, roster, (2, 4))
    a, b = _volunteers_in(db, roster, [chore, other], ["A", "B"])
    chore_tick.run_tick(db, TODAY)
    by_date: dict[date, list[str]] = {}
    for s in db.query(Shift).all():
        by_date.setdefault(s.on_date, []).append(s.volunteer_id)
    assert by_date and all(sorted(v) == sorted([a.id, b.id]) for v in by_date.values())


def test_lone_volunteer_is_double_booked_rather_than_left_open(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    other = _second_chore(db, roster, (2,))
    (solo,) = _volunteers_in(db, roster, [chore, other], ["S"])
    chore_tick.run_tick(db, TODAY)
    shifts = db.query(Shift).all()
    assert len(shifts) == 8  # 4 Wednesdays × 2 chores
    assert all(s.status == "scheduled" and s.volunteer_id == solo.id for s in shifts)


def test_cover_orphaned_prefers_a_volunteer_free_that_day(db):
    roster, chore = _roster(db, cycle_slots=(2,))
    other = _second_chore(db, roster, (2,))
    _volunteers_in(db, roster, [chore, other], ["A", "B"])
    chore_tick.run_tick(db, TODAY)
    on_date = WEEKLY_WED[0]
    mine = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == on_date).one()
    theirs = db.query(Shift).filter(Shift.chore_id == other.id, Shift.on_date == on_date).one()
    freed = mine.volunteer_id
    mine.volunteer_id = None
    db.flush()
    chore_tick.cover_orphaned_shifts(db, roster.id, TODAY)
    db.expire_all()
    # Re-covered by the volunteer with no other shift that day, not by
    # whoever happens to top this chore's independent WRH ranking.
    assert mine.volunteer_id == freed and mine.volunteer_id != theirs.volunteer_id


def test_daily_ticks_never_flip_a_pinned_assignee(db):
    from datetime import timedelta

    roster, chore = _roster(db, cycle_slots=(2,))
    _volunteers_in(db, roster, [chore], ["A", "B", "C"])
    chore_tick.run_tick(db, TODAY)
    promised = {s.id: s.volunteer_id for s in db.query(Shift).all()}
    for day in range(1, 15):
        chore_tick.run_tick(db, TODAY + timedelta(days=day))
    for s in db.query(Shift).filter(Shift.id.in_(promised)).all():
        assert s.volunteer_id == promised[s.id]


def test_covering_rests_the_coverer_in_new_pins(db):
    # A and B alternate. B takes over all of A's pinned turns; when the
    # horizon extends, the fold sees B's extra work and hands A the new
    # pins until the clocks even out.
    roster, chore = _roster(db, cycle_slots=(2,))
    a, b = _volunteers_in(db, roster, [chore], ["A", "B"])
    chore_tick.run_tick(db, TODAY)
    for s in db.query(Shift).all():
        s.volunteer_id = b.id
    db.commit()
    roster.commit_horizon_days = 56
    db.commit()
    chore_tick.run_tick(db, TODAY)
    new_pins = db.query(Shift).filter(Shift.on_date > WEEKLY_WED[-1]).order_by(Shift.on_date).all()
    assert len(new_pins) == 4
    assert all(s.volunteer_id == a.id for s in new_pins)


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
