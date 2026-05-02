"""Daily catch-up for dispatches whose channel window has long
passed.

If the worker is down across the entire 72-hour pre-event window
(REMINDER) or the post-event quiet period (FEEDBACK), dispatch
rows stay ``pending`` forever — the regular sweep filter
excludes them once the window has closed.
``mail_lifecycle.reap_expired()`` finalises those rows: status
flips to FAILED, ``encrypted_email`` nulls in the same UPDATE.
The row stays in the table as a terminal-state record of "we
tried but the window had passed."
"""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, has_any_ciphertext, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus
from backend.services import mail_lifecycle


def test_reap_finalises_expired_pending_reminder(db: Any) -> None:
    """Event already started, reminder still pending → finalise."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    finalised = mail_lifecycle.reap_expired()
    assert finalised == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None
        assert d.status == EmailStatus.FAILED
        assert d.encrypted_email is None
    finally:
        fresh.close()


def test_reap_skips_events_still_in_future(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    assert mail_lifecycle.reap_expired() == 0

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reap_skips_already_settled_dispatches(db: Any) -> None:
    """Reminder already sent → nothing to reap (and we wouldn't
    want to disturb a row whose status is informative)."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test", reminder="sent")
    commit(db)

    assert mail_lifecycle.reap_expired() == 0

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_reap_wipes_ciphertext_when_only_channel_pending(db: Any) -> None:
    """Reminder-only event: once the reminder dispatch is
    finalised, no pending dispatch carries an address → no
    ciphertext anywhere for this signup."""
    e = make_event(db, starts_in=timedelta(hours=-1), feedback_enabled=False)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    mail_lifecycle.reap_expired()

    fresh = SessionLocal()
    try:
        assert not has_any_ciphertext(fresh, s)
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.FAILED
    finally:
        fresh.close()


def test_reap_keeps_feedback_ciphertext_when_event_still_recent(db: Any) -> None:
    """Reminder reaped, but the event ended only just now —
    feedback's window is still open. The feedback dispatch keeps
    its ciphertext so the worker can decrypt later."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    mail_lifecycle.reap_expired()

    fresh = SessionLocal()
    try:
        assert has_any_ciphertext(fresh, s)
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.FAILED
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reap_subsequent_run_is_idempotent(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=-1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert mail_lifecycle.reap_expired() == 1
    assert mail_lifecycle.reap_expired() == 0


def test_reap_with_clock_advanced_past_window(db: Any, clock: Any) -> None:
    """Use the frozen clock to step past the 72h window:
    1. Set time to 'now'; create event 24h out (in window).
    2. Advance clock 48h — event has now started.
    3. Reaper picks it up."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    # Before advancing, the regular sweep would handle it.
    assert mail_lifecycle.reap_expired() == 0

    clock.advance(hours=48)
    assert mail_lifecycle.reap_expired() == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.FAILED
    finally:
        fresh.close()
