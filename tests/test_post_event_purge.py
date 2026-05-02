"""Daily privacy backstop: ≥7 days after an event ends, transition
any still-pending dispatch to FAILED — which under R5 also nulls
``encrypted_email`` in the same UPDATE.

Under normal operation every other path (successful send,
toggle-off cleanup, partial-send reaper, expired-window reaper)
already finalises the dispatch. This sweep is the safety net that
catches anything they missed (worker bug, dropped commit,
multi-day cron outage)."""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import has_any_ciphertext, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailDispatch, EmailStatus
from backend.services import mail_lifecycle


def test_purge_finalises_pending_for_old_event(db: Any) -> None:
    """Event ended 8 days ago, dispatch still pending → finalise +
    null ciphertext. ``make_signup`` here seeds only the FEEDBACK
    row (reminder is moot for a past event); the purge transitions
    the one pending dispatch to FAILED."""
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    s = make_signup(db, e, email="alice@example.test", reminder=False)
    commit(db)

    finalised = mail_lifecycle.reap_expired()
    assert finalised == 1

    fresh = SessionLocal()
    try:
        # Pending dispatch transitioned to FAILED; ciphertext nulled.
        d = fresh.query(EmailDispatch).filter(EmailDispatch.event_id == s.event_id).one()
        assert d.status == EmailStatus.FAILED
        assert d.encrypted_email is None
        assert not has_any_ciphertext(fresh, s)
    finally:
        fresh.close()


def test_purge_skips_recent_event(db: Any) -> None:
    """Event ended 3 days ago — under the 7-day cutoff. Other
    paths still have a chance to run; don't pre-empt them."""
    e = make_event(db, starts_in=timedelta(days=-4), duration=timedelta(hours=2))
    s = make_signup(db, e, email="alice@example.test", reminder=False)
    commit(db)

    finalised = mail_lifecycle.reap_expired()
    assert finalised == 0

    fresh = SessionLocal()
    try:
        # Pending dispatch left alone — ciphertext intact.
        assert has_any_ciphertext(fresh, s)
    finally:
        fresh.close()


def test_purge_skips_signup_without_dispatch(db: Any) -> None:
    """Old event but signup never had an email — no dispatch row
    exists, nothing to purge."""
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    s = make_signup(db, e, email=None)
    commit(db)

    assert mail_lifecycle.reap_expired() == 0

    fresh = SessionLocal()
    try:
        assert not has_any_ciphertext(fresh, s)
    finally:
        fresh.close()


def test_purge_idempotent_on_repeat_run(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    make_signup(db, e, email="alice@example.test", reminder=False)
    commit(db)

    assert mail_lifecycle.reap_expired() == 1
    assert mail_lifecycle.reap_expired() == 0


def test_purge_handles_mixed_events(db: Any) -> None:
    """One old event + one recent event, both with pending
    dispatches. Only the old one's dispatch is finalised."""
    old = make_event(db, starts_in=timedelta(days=-9), duration=timedelta(hours=2))
    recent = make_event(db, starts_in=timedelta(days=-2), duration=timedelta(hours=2))
    s_old = make_signup(db, old, email="alice@example.test", display_name="A", reminder=False)
    s_recent = make_signup(db, recent, email="bob@example.test", display_name="B", reminder=False)
    commit(db)

    assert mail_lifecycle.reap_expired() == 1

    fresh = SessionLocal()
    try:
        # Old: finalised + ciphertext gone.
        assert not has_any_ciphertext(fresh, s_old)
        # Recent: still pending + ciphertext present.
        assert has_any_ciphertext(fresh, s_recent)
    finally:
        fresh.close()


def test_purge_with_clock_advance_crosses_cutoff(db: Any, clock: Any) -> None:
    """Event ends now; before 7d, purge skips. After 7d, purge fires."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(hours=-2), duration=timedelta(hours=1))
    make_signup(db, e, email="alice@example.test", reminder=False)
    commit(db)

    # Just-ended: still inside the 7-day window.
    assert mail_lifecycle.reap_expired() == 0

    clock.advance(days=7, hours=2)
    assert mail_lifecycle.reap_expired() == 1


def test_purge_is_a_backstop_for_stuck_pending(db: Any) -> None:
    """The failure mode the backstop exists for: an event has
    ended ≥7 days ago and the per-channel finalise never ran
    (worker bug, dropped commit, multi-day cron outage). The
    backstop transitions the orphaned pending row to FAILED;
    the same UPDATE nulls ``encrypted_email`` so the privacy
    contract holds even when every other path failed."""
    e = make_event(
        db,
        starts_in=timedelta(days=-9),
        duration=timedelta(hours=2),
        feedback_enabled=True,
    )
    s = make_signup(db, e, email="alice@example.test", feedback="pending", reminder=False)
    commit(db)

    finalised = mail_lifecycle.reap_expired()
    assert finalised == 1

    fresh = SessionLocal()
    try:
        d = (
            fresh.query(EmailDispatch)
            .filter(
                EmailDispatch.event_id == s.event_id,
                EmailDispatch.channel == EmailChannel.FEEDBACK,
            )
            .one()
        )
        assert d.status == EmailStatus.FAILED
        assert d.encrypted_email is None
    finally:
        fresh.close()
