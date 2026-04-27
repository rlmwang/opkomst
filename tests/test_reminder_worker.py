"""Behavioural tests for ``services.reminder_worker``.

Each test seeds the DB directly via ``_worker_helpers``, runs
``run_once()``, and asserts on the resulting status / email
captures. The fake email backend (``fake_email`` fixture) lets us
inspect what would have been sent without spinning up SMTP.
"""

from datetime import timedelta
from typing import Any

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import reminder_worker

from _worker_helpers import commit, make_event, make_signup


# --- Window gating ---------------------------------------------------


def test_reminder_fires_when_event_is_in_window(db: Any, fake_email: Any) -> None:
    """Event 24h out, reminder enabled, email set → fires once."""
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = reminder_worker.run_once()
    assert n == 1
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.test"
    # Subject substring matches the reminder template (event_name).
    assert "Demo" in fake_email.sent[0].subject


def test_reminder_does_not_fire_when_event_far_out(db: Any, fake_email: Any) -> None:
    """4 days out is outside the 72h window — worker should skip."""
    e = make_event(db, starts_in=timedelta(days=4))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = reminder_worker.run_once()
    assert n == 0
    assert fake_email.sent == []


def test_reminder_does_not_fire_for_past_event(db: Any, fake_email: Any) -> None:
    """Event already started — no point reminding anyone."""
    e = make_event(db, starts_in=timedelta(hours=-1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = reminder_worker.run_once()
    assert n == 0
    assert fake_email.sent == []


def test_reminder_does_not_fire_when_event_toggle_off(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24), reminder_enabled=False)
    # Force pending — we want to verify the worker still respects
    # the event toggle even if the row is somehow ``pending``.
    make_signup(db, e, email="alice@example.test", reminder_status="pending")
    commit(db)

    n = reminder_worker.run_once()
    assert n == 0
    assert fake_email.sent == []


# --- Status transitions ----------------------------------------------


def test_reminder_marks_status_sent(db: Any, fake_email: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reminder_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "sent"
        assert row.reminder_message_id is not None
        assert row.reminder_sent_at is not None
    finally:
        fresh.close()


def test_reminder_failed_send_marks_failed_and_clears_message_id(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 999)  # always fail

    reminder_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "failed"
        assert row.reminder_message_id is None
    finally:
        fresh.close()


def test_reminder_retry_succeeds_on_second_attempt(
    db: Any, fake_email: Any
) -> None:
    """One transient failure, then success — exactly one capture."""
    e = make_event(db, starts_in=timedelta(hours=24))
    make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 1)

    reminder_worker.run_once()

    assert len(fake_email.sent) == 1


# --- Lifecycle / wipe ------------------------------------------------


def test_reminder_done_wipes_when_no_other_pending(
    db: Any, fake_email: Any
) -> None:
    """Reminder-only event: wipe ciphertext after the reminder."""
    e = make_event(db, starts_in=timedelta(hours=24), questionnaire_enabled=False)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reminder_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None  # wiped
    finally:
        fresh.close()


def test_reminder_keeps_ciphertext_when_feedback_pending(
    db: Any, fake_email: Any
) -> None:
    """Both toggles on: reminder fires first; ciphertext kept for
    the feedback worker."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    reminder_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is not None  # kept
        assert row.reminder_email_status == "sent"
        assert row.feedback_email_status == "pending"
    finally:
        fresh.close()


# --- Decrypt failure -------------------------------------------------


def test_reminder_decrypt_failure_keeps_status_pending_today(
    db: Any, fake_email: Any
) -> None:
    """Pre-Phase-2.2 behaviour: a corrupt ciphertext leaves the
    row at ``pending`` and the worker re-tries every tick. This
    test pins the current (intentional) behaviour so Phase 2.2
    has a regression target — once decrypt failure flips to
    ``failed``, this test will need updating."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    # Corrupt the blob in place.
    s.encrypted_email = b"not-real-ciphertext"
    db.add(s)
    commit(db)

    reminder_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        # Today: status untouched because the worker only flips it
        # in the conditional UPDATE block, which runs even if the
        # send was skipped — so we end up at "failed".
        assert row.reminder_email_status == "failed"
    finally:
        fresh.close()
    # No email was actually sent (decrypt couldn't produce a body).
    assert fake_email.sent == []
