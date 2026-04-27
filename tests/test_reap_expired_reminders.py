"""Phase 3.1 — daily catch-up for reminders that missed the window.

If the worker is down across the entire 72-hour pre-event window,
the row stays ``reminder_email_status='pending'`` forever — the
regular sweep's filter excludes events whose ``starts_at`` is in
the past. ``reminder_worker.reap_expired`` fixes that.
"""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import reminder_worker


def test_reap_flips_expired_pending_to_not_applicable(db: Any) -> None:
    """Event already started, reminder still pending → retire."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reaped = reminder_worker.reap_expired()
    assert reaped == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "not_applicable"
    finally:
        fresh.close()


def test_reap_skips_events_still_in_future(db: Any) -> None:
    """Future event, pending reminder → leave alone for the
    regular sweep to handle."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reaped = reminder_worker.reap_expired()
    assert reaped == 0

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "pending"
    finally:
        fresh.close()


def test_reap_skips_already_settled_rows(db: Any) -> None:
    """Row that's already ``sent``/``failed``/``not_applicable``
    is left untouched — the reaper only acts on ``pending``."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(
        db,
        e,
        email="alice@example.test",
        reminder_status="sent",
    )
    commit(db)

    reaped = reminder_worker.reap_expired()
    assert reaped == 0

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "sent"
    finally:
        fresh.close()


def test_reap_wipes_ciphertext_when_only_channel_pending(db: Any) -> None:
    """Reminder-only event (questionnaire off): once the reminder
    is retired, ciphertext has nothing left to wait for and gets
    wiped on the spot."""
    e = make_event(
        db,
        starts_in=timedelta(hours=-1),
        questionnaire_enabled=False,
    )
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reminder_worker.reap_expired()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "not_applicable"
        assert row.encrypted_email is None
    finally:
        fresh.close()


def test_reap_keeps_ciphertext_when_feedback_still_pending(db: Any) -> None:
    """Feedback hasn't fired yet — ciphertext must stay so the
    feedback worker can still decrypt it."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reminder_worker.reap_expired()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "not_applicable"
        assert row.feedback_email_status == "pending"
        assert row.encrypted_email is not None
    finally:
        fresh.close()


def test_reap_subsequent_run_is_idempotent(db: Any) -> None:
    """Run twice — second run finds nothing because the first
    already retired everything."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert reminder_worker.reap_expired() == 1
    assert reminder_worker.reap_expired() == 0


def test_reap_with_clock_advanced_past_window(db: Any, clock: Any) -> None:
    """Use the frozen clock to step past the 72h window:
    1. Set time to 'now'; create event 24h out (in window).
    2. Advance clock by 48h — event has now started.
    3. Reaper should pick it up."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(hours=24))  # event 2026-04-29 12:00
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    # Before advancing, the regular sweep would handle it. Skip
    # the sweep to focus on the reaper.
    assert reminder_worker.reap_expired() == 0

    clock.advance(hours=48)  # now 2026-04-30 12:00 — event ended
    assert reminder_worker.reap_expired() == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "not_applicable"
    finally:
        fresh.close()
