"""Boot-time + hourly reaper for stuck mid-send dispatches.

When a worker process crashes between persisting the message_id
and getting the SMTP ack (or between ack and the final status
flip), the dispatch row is left ``status='pending'`` AND
``message_id IS NOT NULL``. The next worker boot calls
``mail_lifecycle.reap_partial_sends(db)`` which flips those rows to
``failed`` so the next sweep doesn't re-process them.
"""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, has_any_ciphertext, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import mail_lifecycle


def _stick(db: Any, signup: Any, channel: EmailChannel) -> None:
    """Mark a dispatch as mid-send by giving it a message_id while
    leaving its status at pending — exactly the shape a crashed
    worker leaves behind."""
    d = get_dispatch(db, signup, channel)
    assert d is not None
    d.message_id = "<stuck@opkomst.nu>"
    db.add(d)


def test_reaper_flips_partial_reminder_to_failed(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    _stick(db, s, EmailChannel.REMINDER)
    commit(db)

    reaped = mail_lifecycle.reap_partial_sends(SessionLocal())
    assert reaped == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None
        assert d.status == EmailStatus.FAILED
        assert d.sent_at is not None
    finally:
        fresh.close()


def test_reaper_flips_partial_feedback_to_failed(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    _stick(db, s, EmailChannel.FEEDBACK)
    commit(db)

    reaped = mail_lifecycle.reap_partial_sends(SessionLocal())
    assert reaped == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d is not None
        assert d.status == EmailStatus.FAILED
    finally:
        fresh.close()


def test_reaper_skips_clean_pending_rows(db: Any) -> None:
    """Pending rows with message_id NULL haven't been claimed by a
    worker yet — leave them alone."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    assert mail_lifecycle.reap_partial_sends(SessionLocal()) == 0

    fresh = SessionLocal()
    try:
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d_r is not None and d_r.status == EmailStatus.PENDING
        assert d_f is not None and d_f.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reaper_subsequent_sweep_does_not_resend(db: Any, fake_email: Any) -> None:
    """End-to-end: stuck row → reaper → next sweep produces zero
    sends because the dispatch is no longer ``pending``."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    _stick(db, s, EmailChannel.REMINDER)
    commit(db)

    mail_lifecycle.reap_partial_sends(SessionLocal())
    mail_lifecycle.run_once(EmailChannel.REMINDER)

    assert fake_email.sent == []


def test_reaper_wipes_ciphertext_when_both_dispatches_settled(
    db: Any,
) -> None:
    """If reaping was the last settling action (feedback already
    sent, reminder was the partial), the wipe fires."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test", feedback="sent")
    _stick(db, s, EmailChannel.REMINDER)
    commit(db)

    mail_lifecycle.reap_partial_sends(SessionLocal())

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert not has_any_ciphertext(fresh, row)
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.FAILED
    finally:
        fresh.close()


def test_reaper_keeps_ciphertext_when_other_dispatch_still_pending(
    db: Any,
) -> None:
    """Reminder reaped to failed; feedback still pending → keep
    ciphertext so the feedback worker can decrypt later."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    _stick(db, s, EmailChannel.REMINDER)
    commit(db)

    mail_lifecycle.reap_partial_sends(SessionLocal())

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert has_any_ciphertext(fresh, row)
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.FAILED
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reaper_stamps_sent_at_breaking_the_hot_loop(db: Any, fake_email: Any) -> None:
    """The reaper must stamp ``sent_at`` along with the status
    flip so the regular sweep can't re-fetch the row by accident.
    Belt-and-braces: the status filter alone is sufficient, but
    keeping sent_at populated keeps the row out of any
    diagnostics that scan ``sent_at IS NULL``."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    _stick(db, s, EmailChannel.FEEDBACK)
    commit(db)

    mail_lifecycle.reap_partial_sends(SessionLocal())

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d is not None
        assert d.status == EmailStatus.FAILED
        assert d.sent_at is not None
    finally:
        fresh.close()

    assert mail_lifecycle.run_once(EmailChannel.FEEDBACK) == 0
    assert fake_email.sent == []
