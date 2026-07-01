"""Chore shift reminders — ``mail_lifecycle.run_chore_reminders``.

Uses the console mail backend (conftest default). Dates are chosen so
the reminder is due regardless of the wall-clock hour: ``on_date`` is
tomorrow with ``reminder_days_before=2`` → the send day (yesterday) is
strictly past, so the 18:00 gate is always cleared.
"""

from datetime import UTC, datetime, timedelta

from backend.models import Chapter, Chore, Roster, Shift, User, Volunteer
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


# NOTE: the "volunteer leaves → shift reopened + reassigned → new assignee
# reminded" case moved out of the tick in task 11 (the tick no longer
# reopens SET-NULL shifts). Immediate reassignment-on-departure — and
# re-reminding the new assignee — is task 13 (on_volunteer_removed); its
# test is re-added there.
