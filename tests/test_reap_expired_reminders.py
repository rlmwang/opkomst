"""Daily catch-up for reminder dispatches that missed the window.

If the worker is down across the entire 72-hour pre-event window,
the dispatch row stays ``pending`` forever — the regular sweep
filter excludes events whose ``starts_at`` is in the past.
``email_reaper.reap_expired_windows()`` deletes those dispatches
(channel no longer applies; nothing useful to send) and wipes the
ciphertext if no other dispatch remains.
"""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, get_dispatch, make_event, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import email_reaper


def test_reap_deletes_expired_pending_reminder(db: Any) -> None:
    """Event already started, reminder still pending → delete."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reaped = email_reaper.reap_expired_windows()
    assert reaped == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d is None  # deleted
    finally:
        fresh.close()


def test_reap_skips_events_still_in_future(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_reaper.reap_expired_windows() == 0

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reap_skips_already_settled_dispatches(db: Any) -> None:
    """Reminder already sent → nothing to reap (and we wouldn't
    want to delete a row whose status is informative)."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test", reminder="sent")
    commit(db)

    assert email_reaper.reap_expired_windows() == 0

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d is not None and d.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_reap_wipes_ciphertext_when_only_channel_pending(db: Any) -> None:
    """Reminder-only event: once the reminder dispatch is deleted,
    no pending dispatch remains → ciphertext wipes on the spot."""
    e = make_event(db, starts_in=timedelta(hours=-1), questionnaire_enabled=False)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_reaper.reap_expired_windows()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None
        assert get_dispatch(fresh, s.id, EmailChannel.REMINDER) is None
    finally:
        fresh.close()


def test_reap_keeps_ciphertext_when_feedback_still_pending(db: Any) -> None:
    """Feedback hasn't fired yet — ciphertext must stay so the
    feedback worker can still decrypt."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_reaper.reap_expired_windows()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is not None
        assert get_dispatch(fresh, s.id, EmailChannel.REMINDER) is None
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
    finally:
        fresh.close()


def test_reap_subsequent_run_is_idempotent(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=-1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_reaper.reap_expired_windows() == 1
    assert email_reaper.reap_expired_windows() == 0


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
    assert email_reaper.reap_expired_windows() == 0

    clock.advance(hours=48)
    assert email_reaper.reap_expired_windows() == 1

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d is None
    finally:
        fresh.close()
