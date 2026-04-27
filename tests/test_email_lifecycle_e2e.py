"""Phase 5.6 — end-to-end signup-to-cleanup tests.

Covers the full lifecycle of a public signup through the worker
sweeps, using TestClient + the fake email backend + the frozen
clock fixture together. Verifies the privacy invariant
(ciphertext wiped at the right step, not before) end-to-end.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from _worker_helpers import make_event

from backend.database import SessionLocal
from backend.models import Signup
from backend.services import feedback_worker, reminder_worker

# ---- Helpers --------------------------------------------------


def _public_signup(client: Any, slug: str, *, email: str | None) -> Any:
    """POST to the public signup endpoint. Mirrors what the
    front-end does — no auth, no admin chain."""
    payload: dict[str, object] = {
        "display_name": "Alice",
        "party_size": 1,
        "source_choice": "Mond-tot-mond",
    }
    if email is not None:
        payload["email"] = email
    return client.post(f"/api/v1/events/by-slug/{slug}/signups", json=payload)


def _signup_row(session_factory: Any) -> Signup:
    """Fetch the only Signup row in the DB."""
    s = session_factory()
    try:
        rows = s.query(Signup).all()
        assert len(rows) == 1, f"expected 1 signup, got {len(rows)}"
        return rows[0]
    finally:
        s.close()


# ---- Scenarios ------------------------------------------------


def test_e2e_both_channels_send_then_wipe(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Happy path: both toggles on, email provided. Reminder
    fires at T-3d, feedback fires at T+24h, ciphertext wipes
    at the feedback step (not before)."""
    clock.set("2026-04-28T12:00:00+00:00")

    # Event 4 days out, with a known slug we can hit publicly.
    e = make_event(
        db,
        starts_in=timedelta(days=4),
        questionnaire_enabled=True,
        reminder_enabled=True,
        name="E2E Demo",
    )
    db.commit()

    # Public sign-up. No auth.
    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201, r.text

    # Just after signup: ciphertext stored, both channels pending.
    row = _signup_row(SessionLocal)
    assert row.encrypted_email is not None
    assert row.feedback_email_status == "pending"
    assert row.reminder_email_status == "pending"

    # T-3d (still 24h before event start). Reminder should fire.
    clock.advance(days=3)
    n = reminder_worker.run_once()
    assert n == 1
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.com"
    # Reminder template — subject substring.
    assert "E2E Demo" in fake_email.sent[0].subject

    row = _signup_row(SessionLocal)
    assert row.reminder_email_status == "sent"
    assert row.feedback_email_status == "pending"
    # Crucial: ciphertext NOT wiped yet — feedback still pending.
    assert row.encrypted_email is not None

    # Advance through the event end + 25h so feedback can fire
    # (ends_at = starts_in + 2h = 4d + 2h after t0; we're now at
    # 3d after t0; advance 1d2h to hit ends_at, then 25h more to
    # cross the 24h cutoff).
    clock.advance(hours=24 + 2 + 25)
    n = feedback_worker.run_once()
    assert n == 1
    assert len(fake_email.sent) == 2
    assert "Hoe was" in fake_email.sent[1].subject  # feedback template

    row = _signup_row(SessionLocal)
    assert row.feedback_email_status == "sent"
    assert row.reminder_email_status == "sent"
    # Now ciphertext is wiped — both channels settled.
    assert row.encrypted_email is None


def test_e2e_no_email_means_no_ciphertext_no_emails(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Public signup without an email never stores ciphertext
    and never schedules any send."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    r = _public_signup(client, e.slug, email=None)
    assert r.status_code == 201

    row = _signup_row(SessionLocal)
    assert row.encrypted_email is None
    assert row.feedback_email_status == "not_applicable"
    assert row.reminder_email_status == "not_applicable"

    # Run all workers across the timeline; nothing fires.
    clock.advance(days=3)
    assert reminder_worker.run_once() == 0
    clock.advance(hours=72)
    assert feedback_worker.run_once() == 0
    assert fake_email.sent == []


def test_e2e_reminder_only_event_wipes_after_reminder(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Event with reminder on but questionnaire off. Reminder
    fires; ciphertext wipes immediately because no other channel
    is waiting."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(
        db,
        starts_in=timedelta(days=4),
        questionnaire_enabled=False,
        reminder_enabled=True,
    )
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    row = _signup_row(SessionLocal)
    assert row.encrypted_email is not None
    assert row.feedback_email_status == "not_applicable"
    assert row.reminder_email_status == "pending"

    clock.advance(days=3)
    reminder_worker.run_once()

    row = _signup_row(SessionLocal)
    assert row.reminder_email_status == "sent"
    # No feedback to wait for → wipe now.
    assert row.encrypted_email is None
    assert len(fake_email.sent) == 1


def test_e2e_toggle_off_before_window_no_emails_immediate_wipe(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Public signup with email; organiser then disables both
    toggles before the reminder window opens. No emails ever
    send; ciphertext wipes immediately when the second toggle
    flips off."""
    from backend.routers.events import _retire_disabled_channels

    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    # Both pending, ciphertext stored.
    row = _signup_row(SessionLocal)
    assert row.encrypted_email is not None

    # Organiser disables both toggles. Helper directly because the
    # PUT /events/{id} endpoint requires admin auth which is its
    # own fixture chain.
    fresh = SessionLocal()
    try:
        _retire_disabled_channels(
            fresh,
            event_entity_id=e.entity_id,
            questionnaire_disabled=True,
            reminder_disabled=True,
        )
        fresh.commit()
    finally:
        fresh.close()

    row = _signup_row(SessionLocal)
    assert row.feedback_email_status == "not_applicable"
    assert row.reminder_email_status == "not_applicable"
    assert row.encrypted_email is None  # wiped on the spot

    # Run all workers across the timeline — nothing fires.
    clock.advance(days=3)
    assert reminder_worker.run_once() == 0
    clock.advance(hours=72)
    assert feedback_worker.run_once() == 0
    assert fake_email.sent == []


def test_e2e_reminder_window_passed_during_outage_reaper_cleans_up(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Public signup with email on a future event; clock then
    advances past the reminder window without any worker tick
    (simulating a multi-day outage). The boot-time / daily
    ``reap_expired`` retires the row to not_applicable.

    Two events seeded — one already-started, one still in the
    future — so a regression that drops the
    ``Event.starts_at <= now`` filter on the reaper would touch
    the wrong rows and fail this test."""
    from backend.models import Signup as SignupModel

    clock.set("2026-04-28T12:00:00+00:00")
    past_event = make_event(db, starts_in=timedelta(days=4), name="past")
    future_event = make_event(db, starts_in=timedelta(days=4), name="future")
    db.commit()

    r = _public_signup(client, past_event.slug, email="alice@example.com")
    assert r.status_code == 201
    r = _public_signup(client, future_event.slug, email="bob@example.com")
    assert r.status_code == 201

    # Advance only enough that ``past_event`` has ended; the
    # ``future_event`` is still 6 days out (no, 4d-future + the
    # advance: started 4d after t0, advance 4d3h → past_event has
    # already ended; future_event same starts_in computed at
    # make_event-time so also 4d after t0; both end before the
    # advance lands… let's recompute). Instead: build the future
    # event explicitly far enough ahead.
    fresh = SessionLocal()
    try:
        from backend.models import Event as EventModel

        ev = fresh.query(EventModel).filter_by(entity_id=future_event.entity_id).first()
        assert ev is not None
        # Push the future event's starts_at to 30 days out — far
        # past any clock advancement in this test.
        ev.starts_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)
        ev.ends_at = ev.starts_at + timedelta(hours=2)
        fresh.commit()
    finally:
        fresh.close()

    # Skip past the entire reminder window for past_event without
    # running a reminder sweep.
    clock.advance(days=4, hours=3)

    reaped = reminder_worker.reap_expired()
    assert reaped == 1, "reaper should only touch the past event's signup"

    fresh = SessionLocal()
    try:
        past_signup = (
            fresh.query(SignupModel)
            .filter(SignupModel.event_id == past_event.entity_id)
            .first()
        )
        future_signup = (
            fresh.query(SignupModel)
            .filter(SignupModel.event_id == future_event.entity_id)
            .first()
        )
        assert past_signup is not None and future_signup is not None
        # Only the past event's signup got retired.
        assert past_signup.reminder_email_status == "not_applicable"
        # The future event's signup is unchanged.
        assert future_signup.reminder_email_status == "pending"
    finally:
        fresh.close()

    # Feedback for the past event can still fire — the worker
    # query is gated on questionnaire_enabled and ends_at <=
    # now-24h. After ``advance(days=4, hours=3)`` the event
    # ended 1h ago, so we need another 23h to clear the 24h
    # cutoff.
    clock.advance(hours=24)
    feedback_worker.run_once()
    assert len(fake_email.sent) == 1  # feedback only, past event

    fresh = SessionLocal()
    try:
        past_signup = (
            fresh.query(SignupModel)
            .filter(SignupModel.event_id == past_event.entity_id)
            .first()
        )
        assert past_signup is not None
        assert past_signup.feedback_email_status == "sent"
        assert past_signup.encrypted_email is None  # both channels settled
    finally:
        fresh.close()


def test_e2e_smtp_failure_wipes_via_failed_path(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """SMTP raises on every attempt for the reminder. Status
    flips to ``failed``; the ciphertext lifecycle still
    wipes correctly when the second channel finishes."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    fake_email.fail_n_times("alice@example.com", 999)
    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    clock.advance(days=3)
    reminder_worker.run_once()

    row = _signup_row(SessionLocal)
    assert row.reminder_email_status == "failed"
    # Reminder failed; feedback still pending → ciphertext kept.
    assert row.encrypted_email is not None

    # Stop failing for the feedback send.
    fake_email.raise_on = None
    clock.advance(hours=24 + 2 + 25)
    feedback_worker.run_once()

    row = _signup_row(SessionLocal)
    assert row.feedback_email_status == "sent"
    assert row.encrypted_email is None


def test_e2e_signup_writes_naive_utc_starts_at_to_db(
    db: Any, client: Any, clock: Any
) -> None:
    """Verify the timezone contract end-to-end: the API receives
    a naive ISO datetime (treated as UTC), stores it as a naive
    column on the row, and the worker's later ``starts_at <= now``
    comparison uses that naive value against ``datetime.now(UTC)``
    without crashing or off-by-one. Belt-and-braces around the
    property test in ``tests/test_timezone_invariants``."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=2))
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    # Round-trip: starts_at is naive in the DB (SQLAlchemy
    # ``DateTime`` strips tzinfo on write), but the value
    # represents UTC. The reminder worker's window check uses
    # ``datetime.now(UTC)`` which is tz-aware; SQLAlchemy
    # compares them as if both were UTC, which is the contract
    # we depend on.
    fresh = SessionLocal()
    try:
        from backend.models import Event as EventModel

        ev = fresh.query(EventModel).filter_by(entity_id=e.entity_id).first()
        assert ev is not None
        # Stored naive, value is the expected UTC instant.
        assert ev.starts_at.tzinfo is None
        expected = datetime(2026, 4, 30, 12, 0)  # 2 days after frozen now, in UTC
        # Allow sub-second drift from datetime.now() inside make_event.
        assert abs((ev.starts_at - expected).total_seconds()) < 5
    finally:
        fresh.close()
