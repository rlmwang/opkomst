"""Daily privacy backstop: ≥7 days after an event ends, force-wipe
any remaining ciphertext for its signups.

Under normal operation every other path (successful send,
toggle-off cleanup, partial-send reaper, expired-window reaper)
already wipes the ciphertext. This sweep is the safety net that
catches anything they missed."""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import email_reaper


def test_purge_wipes_ciphertext_for_old_event(db: Any) -> None:
    """Event ended 8 days ago, signup still has encrypted_email
    set somehow → wipe."""
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    wiped = email_reaper.purge_post_event_emails()
    assert wiped == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None
    finally:
        fresh.close()


def test_purge_skips_recent_event(db: Any) -> None:
    """Event ended 3 days ago — under the 7-day cutoff. Other
    paths still have a chance to run; don't pre-empt them."""
    e = make_event(db, starts_in=timedelta(days=-4), duration=timedelta(hours=2))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    wiped = email_reaper.purge_post_event_emails()
    assert wiped == 0

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is not None
    finally:
        fresh.close()


def test_purge_skips_signup_without_ciphertext(db: Any) -> None:
    """Old event but signup never had an email — nothing to do."""
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    s = make_signup(db, e, email=None)
    commit(db)

    assert email_reaper.purge_post_event_emails() == 0

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None  # never had one
    finally:
        fresh.close()


def test_purge_idempotent_on_repeat_run(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_reaper.purge_post_event_emails() == 1
    assert email_reaper.purge_post_event_emails() == 0


def test_purge_handles_mixed_events(db: Any) -> None:
    """One old event + one recent event, both with ciphertext.
    Only the old one gets wiped."""
    old = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    recent = make_event(db, starts_in=timedelta(days=-2), duration=timedelta(hours=2))
    s_old = make_signup(db, old, email="alice@example.test", display_name="A")
    s_recent = make_signup(db, recent, email="bob@example.test", display_name="B")
    commit(db)

    assert email_reaper.purge_post_event_emails() == 1

    fresh = SessionLocal()
    try:
        row_old = fresh.query(Signup).filter(Signup.id == s_old.id).first()
        row_recent = fresh.query(Signup).filter(Signup.id == s_recent.id).first()
        assert row_old is not None and row_old.encrypted_email is None
        assert row_recent is not None and row_recent.encrypted_email is not None
    finally:
        fresh.close()


def test_purge_with_clock_advance_crosses_cutoff(
    db: Any, clock: Any
) -> None:
    """Event ends now; before 7d, purge skips. After 7d, purge wipes."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(hours=-2), duration=timedelta(hours=1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    # Just-ended: still inside the 7-day window.
    assert email_reaper.purge_post_event_emails() == 0

    clock.advance(days=7, hours=2)
    assert email_reaper.purge_post_event_emails() == 1


def test_purge_is_a_backstop_with_pending_dispatches(db: Any) -> None:
    """Simulate the failure mode the backstop exists for: an event
    has ended ≥7 days ago, the per-channel wipe never ran (a bug in
    the dispatcher, a deploy that was rolled back mid-flight,
    whatever), so the signup still has ciphertext AND a pending
    dispatch row. The backstop must wipe the ciphertext AND
    finalise the orphaned pending row to FAILED — leaving a
    pending row with no ciphertext would break the wipe invariant
    (``encrypted_email IS NULL`` ⇔ no PENDING dispatch row)."""
    from backend.models import EmailStatus, SignupEmailDispatch

    e = make_event(
        db,
        starts_in=timedelta(days=-9),
        duration=timedelta(hours=2),
        questionnaire_enabled=True,
    )
    # ``feedback="pending"`` deliberately leaves a pending row to
    # simulate the not-cleaned-up state.
    s = make_signup(db, e, email="alice@example.test", feedback="pending")
    commit(db)

    wiped = email_reaper.purge_post_event_emails()
    assert wiped == 1

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None and row.encrypted_email is None
        # The orphaned pending row must have been transitioned to
        # FAILED — otherwise the wipe invariant breaks.
        pending = (
            fresh.query(SignupEmailDispatch)
            .filter(
                SignupEmailDispatch.signup_id == s.id,
                SignupEmailDispatch.status == EmailStatus.PENDING,
            )
            .count()
        )
        assert pending == 0, "purge left a pending dispatch behind"
    finally:
        fresh.close()
