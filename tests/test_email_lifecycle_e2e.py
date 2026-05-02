"""End-to-end signup-to-cleanup tests.

Covers the full lifecycle of a public signup through the dispatcher
sweeps, using TestClient + the fake email backend + the frozen
clock fixture together. Verifies the privacy invariant
(ciphertext wiped at the right step, not before) end-to-end.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from _helpers.events import make_event
from _helpers.signups import get_dispatch, has_any_ciphertext

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import mail_lifecycle

# ---- Helpers --------------------------------------------------


def _public_signup(client: Any, slug: str, *, email: str | None) -> Any:
    payload: dict[str, object] = {
        "display_name": "Alice",
        "party_size": 1,
        "source_choice": "Mond-tot-mond",
    }
    if email is not None:
        payload["email"] = email
    return client.post(f"/api/v1/events/by-slug/{slug}/signups", json=payload)


def _signup_row(session_factory: Any) -> Signup:
    s = session_factory()
    try:
        rows = s.query(Signup).all()
        assert len(rows) == 1, f"expected 1 signup, got {len(rows)}"
        return rows[0]
    finally:
        s.close()


# ---- Scenarios ------------------------------------------------


def test_e2e_both_channels_send_then_wipe(db: Any, client: Any, fake_email: Any, clock: Any) -> None:
    """Both toggles on, email provided. Reminder fires at T-3d,
    feedback fires at T+24h, ciphertext wipes at the feedback step."""
    clock.set("2026-04-28T12:00:00+00:00")

    e = make_event(
        db,
        starts_in=timedelta(days=4),
        feedback_enabled=True,
        reminder_enabled=True,
        name="E2E Demo",
    )
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201, r.text

    # Just after signup: ciphertext stored, both dispatches pending.
    row = _signup_row(SessionLocal)
    assert has_any_ciphertext(db, row)
    fresh = SessionLocal()
    try:
        d_r = get_dispatch(fresh, row, EmailChannel.REMINDER)
        d_f = get_dispatch(fresh, row, EmailChannel.FEEDBACK)
        assert d_r is not None and d_r.status == EmailStatus.PENDING
        assert d_f is not None and d_f.status == EmailStatus.PENDING
    finally:
        fresh.close()

    clock.advance(days=3)
    n = mail_lifecycle.run_once(EmailChannel.REMINDER)
    assert n == 1
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.com"
    assert "E2E Demo" in fake_email.sent[0].subject

    fresh = SessionLocal()
    try:
        d_r = get_dispatch(fresh, row, EmailChannel.REMINDER)
        d_f = get_dispatch(fresh, row, EmailChannel.FEEDBACK)
        assert d_r is not None and d_r.status == EmailStatus.SENT
        assert d_f is not None and d_f.status == EmailStatus.PENDING
        # Ciphertext NOT wiped — feedback still pending.
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()

    clock.advance(hours=24 + 2 + 25)
    n = mail_lifecycle.run_once(EmailChannel.FEEDBACK)
    assert n == 1
    assert len(fake_email.sent) == 2
    assert "Hoe was" in fake_email.sent[1].subject

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, row, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.SENT
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert not has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()


def test_e2e_no_email_means_no_ciphertext_no_dispatches(db: Any, client: Any, fake_email: Any, clock: Any) -> None:
    """Public signup without an email never stores ciphertext
    and never creates any dispatch row."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    r = _public_signup(client, e.slug, email=None)
    assert r.status_code == 201

    row = _signup_row(SessionLocal)
    assert not has_any_ciphertext(db, row)
    fresh = SessionLocal()
    try:
        assert get_dispatch(fresh, row, EmailChannel.REMINDER) is None
        assert get_dispatch(fresh, row, EmailChannel.FEEDBACK) is None
    finally:
        fresh.close()

    clock.advance(days=3)
    assert mail_lifecycle.run_once(EmailChannel.REMINDER) == 0
    clock.advance(hours=72)
    assert mail_lifecycle.run_once(EmailChannel.FEEDBACK) == 0
    assert fake_email.sent == []


def test_e2e_reminder_only_event_wipes_after_reminder(db: Any, client: Any, fake_email: Any, clock: Any) -> None:
    """Event with reminder on but questionnaire off. Reminder
    fires; ciphertext wipes immediately because no other dispatch
    is waiting."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(
        db,
        starts_in=timedelta(days=4),
        feedback_enabled=False,
        reminder_enabled=True,
    )
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    row = _signup_row(SessionLocal)
    assert has_any_ciphertext(db, row)
    fresh = SessionLocal()
    try:
        assert get_dispatch(fresh, row, EmailChannel.FEEDBACK) is None
        d_r = get_dispatch(fresh, row, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.PENDING
    finally:
        fresh.close()

    clock.advance(days=3)
    mail_lifecycle.run_once(EmailChannel.REMINDER)

    fresh = SessionLocal()
    try:
        d_r = get_dispatch(fresh, row, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.SENT
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert not has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()
    assert len(fake_email.sent) == 1


def test_e2e_toggle_off_before_window_no_emails_immediate_wipe(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Public signup with email; organiser then disables both
    toggles before the reminder window opens. No emails ever
    send; ciphertext wipes immediately when both dispatches are
    retired."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    row = _signup_row(SessionLocal)
    assert has_any_ciphertext(db, row)

    fresh = SessionLocal()
    try:
        mail_lifecycle.retire_event_channels(
            fresh,
            event_id=e.id,
            channels={EmailChannel.REMINDER, EmailChannel.FEEDBACK},
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        assert get_dispatch(fresh, row, EmailChannel.REMINDER) is None
        assert get_dispatch(fresh, row, EmailChannel.FEEDBACK) is None
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert not has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()

    clock.advance(days=3)
    assert mail_lifecycle.run_once(EmailChannel.REMINDER) == 0
    clock.advance(hours=72)
    assert mail_lifecycle.run_once(EmailChannel.FEEDBACK) == 0
    assert fake_email.sent == []


def test_e2e_reminder_window_passed_during_outage_reaper_cleans_up(
    db: Any, client: Any, fake_email: Any, clock: Any
) -> None:
    """Public signup with email on a future event; clock then
    advances past the reminder window without any worker tick
    (multi-day outage). The daily ``reap_expired`` finalises the
    stranded reminder dispatch (status=FAILED + ciphertext nulled
    in one UPDATE).

    Two events seeded — one already-started, one still in the
    future — so a regression that drops the
    ``Event.starts_at <= now`` filter would touch the wrong rows."""
    clock.set("2026-04-28T12:00:00+00:00")
    past_event = make_event(db, starts_in=timedelta(days=4), name="past")
    future_event = make_event(db, starts_in=timedelta(days=4), name="future")
    db.commit()

    r = _public_signup(client, past_event.slug, email="alice@example.com")
    assert r.status_code == 201
    r = _public_signup(client, future_event.slug, email="bob@example.com")
    assert r.status_code == 201

    fresh = SessionLocal()
    try:
        from backend.models import Event as EventModel

        ev = fresh.query(EventModel).filter_by(id=future_event.id).first()
        assert ev is not None
        ev.starts_at = datetime.now(UTC) + timedelta(days=30)
        ev.ends_at = ev.starts_at + timedelta(hours=2)
        fresh.commit()
    finally:
        fresh.close()

    clock.advance(days=4, hours=3)

    reaped = mail_lifecycle.reap_expired()
    assert reaped == 1, "reaper should only touch the past event's signup"

    fresh = SessionLocal()
    try:
        past_signup = fresh.query(Signup).filter(Signup.event_id == past_event.id).first()
        future_signup = fresh.query(Signup).filter(Signup.event_id == future_event.id).first()
        assert past_signup is not None and future_signup is not None
        d_past = get_dispatch(fresh, past_signup, EmailChannel.REMINDER)
        assert d_past is not None and d_past.status == EmailStatus.FAILED
        assert d_past.encrypted_email is None
        d_future = get_dispatch(fresh, future_signup, EmailChannel.REMINDER)
        assert d_future is not None and d_future.status == EmailStatus.PENDING
    finally:
        fresh.close()

    # Feedback for the past event can still fire — gated on
    # ends_at <= now-24h.
    clock.advance(hours=24)
    mail_lifecycle.run_once(EmailChannel.FEEDBACK)
    assert len(fake_email.sent) == 1

    fresh = SessionLocal()
    try:
        past_signup = fresh.query(Signup).filter(Signup.event_id == past_event.id).first()
        assert past_signup is not None
        d_f = get_dispatch(fresh, past_signup, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.SENT
        # Both dispatches settled (reminder deleted, feedback sent)
        # → ciphertext wiped.
        assert not has_any_ciphertext(fresh, past_signup)
    finally:
        fresh.close()


def test_e2e_smtp_failure_wipes_via_failed_path(db: Any, client: Any, fake_email: Any, clock: Any) -> None:
    """SMTP raises on every attempt for the reminder. Status
    flips to ``failed``; the ciphertext lifecycle still
    wipes correctly when the second dispatch finishes."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=4))
    db.commit()

    fake_email.fail_n_times("alice@example.com", 999)
    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    clock.advance(days=3)
    mail_lifecycle.run_once(EmailChannel.REMINDER)

    row = _signup_row(SessionLocal)
    fresh = SessionLocal()
    try:
        d_r = get_dispatch(fresh, row, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.FAILED
        # Reminder failed; feedback still pending → ciphertext kept.
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()

    fake_email.raise_on = None
    clock.advance(hours=24 + 2 + 25)
    mail_lifecycle.run_once(EmailChannel.FEEDBACK)

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, row, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.SENT
        row_now = fresh.query(Signup).filter(Signup.id == row.id).first()
        assert row_now is not None
        assert not has_any_ciphertext(fresh, row_now)
    finally:
        fresh.close()


def test_e2e_signup_writes_aware_utc_starts_at_to_db(db: Any, client: Any, clock: Any) -> None:
    """Verify the timezone contract end-to-end. Every datetime
    column is now ``TIMESTAMPTZ``; the value round-trips as
    tz-aware UTC."""
    clock.set("2026-04-28T12:00:00+00:00")
    e = make_event(db, starts_in=timedelta(days=2))
    db.commit()

    r = _public_signup(client, e.slug, email="alice@example.com")
    assert r.status_code == 201

    fresh = SessionLocal()
    try:
        from backend.models import Event as EventModel

        ev = fresh.query(EventModel).filter_by(id=e.id).first()
        assert ev is not None
        assert ev.starts_at.tzinfo is not None
        expected = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
        assert abs((ev.starts_at - expected).total_seconds()) < 5
    finally:
        fresh.close()
