"""Phase 2.1 — boot-time reaper.

When a worker process crashes between persisting the message_id
and getting the SMTP ack (or between ack and the final status
flip), the row is left ``status == 'pending'`` AND
``message_id IS NOT NULL``. The next worker boot calls
``email_lifecycle.reap_partial_sends(db)`` which flips those rows
to ``failed`` so the next sweep doesn't re-process them.
"""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import email_lifecycle, reminder_worker


def test_reaper_flips_partial_reminder_to_failed(db: Any) -> None:
    """Row with reminder_email_status='pending' AND message_id set
    is a stuck partial send — reap to 'failed'."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    # Simulate a crash between pre-mint commit and SMTP ack.
    s.reminder_message_id = "<stuck@opkomst.nu>"
    db.add(s)
    commit(db)

    reaped = email_lifecycle.reap_partial_sends(SessionLocal())
    assert reaped == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "failed"
    finally:
        fresh.close()


def test_reaper_flips_partial_feedback_to_failed(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    s.feedback_message_id = "<stuck@opkomst.nu>"
    db.add(s)
    commit(db)

    reaped = email_lifecycle.reap_partial_sends(SessionLocal())
    assert reaped == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "failed"
    finally:
        fresh.close()


def test_reaper_skips_clean_pending_rows(db: Any) -> None:
    """Pending rows with message_id NULL haven't been touched by a
    worker yet — leave them alone so the next sweep handles them
    normally."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reaped = email_lifecycle.reap_partial_sends(SessionLocal())
    assert reaped == 0

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "pending"
        assert row.feedback_email_status == "pending"
    finally:
        fresh.close()


def test_reaper_subsequent_sweep_does_not_resend(
    db: Any, fake_email: Any
) -> None:
    """End-to-end: stuck row → reaper → next sweep produces zero
    sends because the row is no longer ``pending``."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    s.reminder_message_id = "<stuck@opkomst.nu>"
    db.add(s)
    commit(db)

    email_lifecycle.reap_partial_sends(SessionLocal())
    reminder_worker.run_once()

    assert fake_email.sent == []


def test_reaper_wipes_ciphertext_when_both_channels_settled(
    db: Any,
) -> None:
    """If reaping was the *last* settling action for a row (e.g.
    feedback already sent, reminder was the partial), the wipe
    fires."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test", feedback_status="sent")
    s.reminder_message_id = "<stuck@opkomst.nu>"
    db.add(s)
    commit(db)

    email_lifecycle.reap_partial_sends(SessionLocal())

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "failed"
        assert row.encrypted_email is None  # both channels settled → wiped
    finally:
        fresh.close()


def test_reaper_stamps_sent_at_so_row_isnt_re_fetched(
    db: Any, fake_email: Any
) -> None:
    """The reaper must stamp ``*_sent_at`` along with the status
    flip, otherwise the regular sweep's ``sent_at IS NULL`` filter
    keeps re-fetching the row every tick. Verifies the invariant
    "settled ⇒ sent_at IS NOT NULL" is upheld by the reaper."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    s.feedback_message_id = "<stuck@opkomst.nu>"
    db.add(s)
    commit(db)

    email_lifecycle.reap_partial_sends(SessionLocal())

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "failed"
        assert row.feedback_sent_at is not None
    finally:
        fresh.close()
