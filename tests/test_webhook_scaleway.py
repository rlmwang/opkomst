"""Phase 5.5 — Scaleway TEM webhook handler.

Covers the auth/signature gate (fail-closed when secret is unset,
401 on signature mismatch, 204 on valid signed payload, 204 on
explicit opt-in unsigned mode), and the channel-aware lookup
(feedback or reminder message_id, bounce vs. complaint event,
unmatched id is logged but doesn't crash).
"""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

import pytest
from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup

# --- Helpers ----------------------------------------------------


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _post_event(client: Any, payload: dict | list, secret: str | None = None) -> Any:
    """POST a JSON payload to the webhook. ``secret`` controls
    signing: if None, no signature header. The body is hashed
    over the *exact* serialised JSON we send so signature
    verification matches."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if secret is not None:
        headers["X-Scaleway-Signature"] = _sign(secret, body)
    return client.post("/api/v1/webhooks/scaleway-email", content=body, headers=headers)


@pytest.fixture(autouse=True)
def _isolate_webhook_env(monkeypatch: Any) -> None:
    """Clear any pre-existing webhook env so each test sets its
    own state explicitly."""
    monkeypatch.delenv("SCALEWAY_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", raising=False)


# --- Signature gating ---------------------------------------------


def test_webhook_fails_closed_when_secret_missing(client: Any) -> None:
    """Phase 1 audit fix — must not regress."""
    r = _post_event(client, {"type": "email_bounce", "message_id": "<x>"})
    assert r.status_code == 503


def test_webhook_returns_401_when_signature_header_missing(
    client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", "abc123")
    r = _post_event(client, {"type": "email_bounce", "message_id": "<x>"})
    assert r.status_code == 401


def test_webhook_returns_401_on_signature_mismatch(
    client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", "abc123")
    body = json.dumps({"type": "email_bounce", "message_id": "<x>"}).encode("utf-8")
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        content=body,
        headers={
            "content-type": "application/json",
            "X-Scaleway-Signature": "deadbeef",
        },
    )
    assert r.status_code == 401


def test_webhook_returns_204_with_valid_signature(
    client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("SCALEWAY_WEBHOOK_SECRET", "abc123")
    r = _post_event(client, {"type": "email_bounce", "message_id": "<x>"}, secret="abc123")
    assert r.status_code == 204


def test_webhook_opt_in_unsigned_bypass(client: Any, monkeypatch: Any) -> None:
    """OPKOMST_ALLOW_UNSIGNED_WEBHOOKS=1 lets dev environments
    fire signature-less posts. Never set in prod."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    r = _post_event(client, {"type": "email_bounce", "message_id": "<x>"})
    assert r.status_code == 204


# --- Status updates by message_id ------------------------------


def _seed_signup_with_message_ids(db: Any) -> Signup:
    """Helper: insert a signup whose ``feedback_message_id`` and
    ``reminder_message_id`` are predictable so we can target them
    from a webhook."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test")
    s.feedback_message_id = "<feedback-abc@opkomst.nu>"
    s.reminder_message_id = "<reminder-xyz@opkomst.nu>"
    s.feedback_email_status = "sent"
    s.reminder_email_status = "sent"
    db.add(s)
    commit(db)
    return s


def test_bounce_on_feedback_id_flips_feedback_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": s.feedback_message_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "bounced"
        # The other channel is untouched.
        assert row.reminder_email_status == "sent"
    finally:
        fresh.close()


def test_bounce_on_reminder_id_flips_reminder_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": s.reminder_message_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "bounced"
        assert row.feedback_email_status == "sent"
    finally:
        fresh.close()


def test_complaint_event_flips_to_complaint(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_spam", "message_id": s.feedback_message_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "complaint"
    finally:
        fresh.close()


def test_unmatched_message_id_is_logged_not_crashed(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    """A message_id from a previous deployment / different DB
    shouldn't cause the webhook to error — log and move on."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": "<never-seen@nowhere>"},
    )
    assert r.status_code == 204


def test_delivery_event_does_not_change_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    """Delivery / open / click / soft bounce events are
    deliberately ignored — we only act on hard failures and
    complaints."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_delivered", "message_id": s.feedback_message_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        # Status untouched — still 'sent' from the seed.
        assert row.feedback_email_status == "sent"
    finally:
        fresh.close()


def test_batch_payload_processes_every_event(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    """Scaleway can post an array of events in one request."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        [
            {"type": "email_bounce", "message_id": s.feedback_message_id},
            {"type": "email_spam", "message_id": s.reminder_message_id},
        ],
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "bounced"
        assert row.reminder_email_status == "complaint"
    finally:
        fresh.close()


def test_event_with_missing_message_id_is_skipped(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    """A webhook event with no message_id can't be correlated to
    any signup — skip it (don't 400) and continue the batch."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        [
            {"type": "email_bounce"},  # no message_id
            {"type": "email_bounce", "message_id": s.feedback_message_id},
        ],
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        # Second event still processed despite the first being malformed.
        assert row.feedback_email_status == "bounced"
    finally:
        fresh.close()
