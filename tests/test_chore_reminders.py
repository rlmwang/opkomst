"""Chore shift reminders — ``mail_lifecycle.run_chore_reminders``.

Uses the console mail backend (conftest default). Dates are chosen so
the reminder is due regardless of the wall-clock hour: ``on_date`` is
tomorrow with ``reminder_days_before=2`` → the send day (yesterday) is
strictly past, so the 18:00 gate is always cleared.
"""

from datetime import UTC, datetime, timedelta

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, User, Volunteer
from backend.services import encryption, mail_lifecycle
from backend.services.events import now_wallclock


def _seed(
    db,
    *,
    days_before=2,
    on_offset=1,
    reminders=True,
    has_email=True,
    roster_archived=False,
    roster_reminders=True,
    hashsuffix="a",
):
    today = now_wallclock().date()
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug=f"rost{hashsuffix}",
        name="Bins roster",
        created_by=user.id,
        chapter_id=chapter.id,
        starts_on=today - timedelta(days=30),
        reminder_enabled=roster_reminders,
        reminder_days_before=days_before,
        archived_at=datetime.now(UTC) if roster_archived else None,
    )
    db.add(roster)
    db.commit()
    chore = Chore(roster_id=roster.id, name="Bins", ordinal=1, cycle_slots=[2])
    db.add(chore)
    db.commit()
    vol = Volunteer(
        roster_id=roster.id,
        display_name="V",
        email_reminders=reminders,
        encrypted_email=encryption.encrypt("v@local.dev") if has_email else None,
        edit_token_hash=f"h{hashsuffix}",
    )
    db.add(vol)
    db.commit()
    shift = Shift(
        chore_id=chore.id,
        on_date=today + timedelta(days=on_offset),
        slot_index=0,
        status="scheduled",
        volunteer_id=vol.id,
    )
    db.add(shift)
    db.commit()
    return roster, chore, vol, shift


def _shift(db, shift_id) -> Shift:
    db.rollback()
    return db.query(Shift).filter(Shift.id == shift_id).one()


def test_sends_within_window(db):
    _, _, _, shift = _seed(db)
    assert mail_lifecycle.run_chore_reminders() == 1
    assert _shift(db, shift.id).reminder_sent_at is not None


def test_idempotent_second_sweep(db):
    _, _, _, shift = _seed(db)
    assert mail_lifecycle.run_chore_reminders() == 1
    assert mail_lifecycle.run_chore_reminders() == 0  # already stamped


def test_not_due_yet(db):
    # Shift 10 days out, 1-day lead → send day is future.
    _, _, _, shift = _seed(db, on_offset=10, days_before=1)
    assert mail_lifecycle.run_chore_reminders() == 0
    assert _shift(db, shift.id).reminder_sent_at is None


def test_opted_out_no_send(db):
    _, _, _, shift = _seed(db, reminders=False)
    assert mail_lifecycle.run_chore_reminders() == 0


def test_no_email_no_send(db):
    _, _, _, shift = _seed(db, has_email=False)
    assert mail_lifecycle.run_chore_reminders() == 0


def test_roster_reminders_off_no_send(db):
    _, _, _, shift = _seed(db, roster_reminders=False)
    assert mail_lifecycle.run_chore_reminders() == 0


def test_archived_roster_no_send(db):
    _, _, _, shift = _seed(db, roster_archived=True)
    assert mail_lifecycle.run_chore_reminders() == 0


def test_send_failure_leaves_stamp_null(db, monkeypatch):
    _, _, _, shift = _seed(db)
    monkeypatch.setattr(mail_lifecycle, "send_with_retry", lambda **kwargs: False)
    assert mail_lifecycle.run_chore_reminders() == 0
    assert _shift(db, shift.id).reminder_sent_at is None


def test_reassigned_shift_reminds_the_new_assignee(db):
    """A shift already reminded for one volunteer, once reopened +
    reassigned, must remind the new assignee (the user-flagged case)."""
    from backend.services import chore_tick

    roster, chore, vol_a, shift = _seed(db)
    # A's reminder already went out.
    assert mail_lifecycle.run_chore_reminders() == 1
    assert _shift(db, shift.id).reminder_sent_at is not None

    # A second eligible volunteer, then A leaves.
    vol_b = Volunteer(
        roster_id=roster.id,
        display_name="B",
        email_reminders=True,
        encrypted_email=encryption.encrypt("b@local.dev"),
        edit_token_hash="hb",
    )
    db.add(vol_b)
    db.commit()
    db.add(Enrollment(volunteer_id=vol_b.id, chore_id=chore.id))
    db.commit()
    db.delete(db.query(Volunteer).filter(Volunteer.id == vol_a.id).one())
    db.commit()

    # Tick reopens the orphaned shift (clearing the stamp) + reassigns B.
    chore_tick.run_tick(db, now_wallclock().date())
    reopened = _shift(db, shift.id)
    assert reopened.volunteer_id == vol_b.id
    assert reopened.reminder_sent_at is None  # stamp cleared on reopen

    # B now gets their own reminder for the reopened shift. (The tick
    # also materialised future shifts for B, so the sweep count may be
    # >1; what matters is this specific shift is now reminded.)
    assert mail_lifecycle.run_chore_reminders() >= 1
    assert _shift(db, shift.id).reminder_sent_at is not None
