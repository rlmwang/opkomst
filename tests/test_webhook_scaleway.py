"""Scaleway TEM webhook handler.

Covers the auth/signature gate and the channel-aware lookup
(single indexed query over ``signup_email_dispatches.message_id``;
no asymmetric "try column A, then column B" ladder).
"""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup

# Webhook env vars (SCALEWAY_WEBHOOK_SECRET, OPKOMST_ALLOW_UNSIGNED_WEBHOOKS)
# are reset before every test by the autouse `_isolate_optional_env`
# fixture in conftest.py.

# --- Helpers ----------------------------------------------------


def _sign(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _post_event(client: Any, payload: dict | list, secret: str | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if secret is not None:
        headers["X-Scaleway-Signature"] = _sign(secret, body)
    return client.post("/api/v1/webhooks/scaleway-email", content=body, headers=headers)


# --- Signature gating ---------------------------------------------


def test_webhook_fails_closed_when_secret_missing(client: Any) -> None:
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
    r = _post_event(
        client, {"type": "email_bounce", "message_id": "<x>"}, secret="abc123"
    )
    assert r.status_code == 204


def test_webhook_opt_in_unsigned_bypass(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    r = _post_event(client, {"type": "email_bounce", "message_id": "<x>"})
    assert r.status_code == 204


# --- Status updates by message_id ------------------------------


def _seed_signup_with_message_ids(db: Any) -> tuple[Signup, str, str]:
    """Insert a signup and pre-populate both dispatch rows with
    known message_ids in status='sent', mimicking a successful
    send for both channels."""
    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test", feedback="sent", reminder="sent")
    feedback_msg_id = "<feedback-abc@opkomst.nu>"
    reminder_msg_id = "<reminder-xyz@opkomst.nu>"
    d_f = get_dispatch(db, s.id, EmailChannel.FEEDBACK)
    d_r = get_dispatch(db, s.id, EmailChannel.REMINDER)
    assert d_f is not None and d_r is not None
    d_f.message_id = feedback_msg_id
    d_r.message_id = reminder_msg_id
    commit(db)
    return s, feedback_msg_id, reminder_msg_id


def test_bounce_on_feedback_id_flips_feedback_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, feedback_msg_id, _ = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": feedback_msg_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        d_r = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d_f is not None and d_f.status == EmailStatus.BOUNCED
        # The other channel is untouched.
        assert d_r is not None and d_r.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_bounce_on_reminder_id_flips_reminder_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, _, reminder_msg_id = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": reminder_msg_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        d_r = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.BOUNCED
        assert d_f is not None and d_f.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_complaint_event_flips_to_complaint(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, feedback_msg_id, _ = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_spam", "message_id": feedback_msg_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.COMPLAINT
    finally:
        fresh.close()


def test_unmatched_message_id_is_logged_not_crashed(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")

    r = _post_event(
        client,
        {"type": "email_bounce", "message_id": "<never-seen@nowhere>"},
    )
    assert r.status_code == 204


def test_delivery_event_does_not_change_status(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, feedback_msg_id, _ = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        {"type": "email_delivered", "message_id": feedback_msg_id},
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.SENT
    finally:
        fresh.close()


def test_batch_payload_processes_every_event(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, feedback_msg_id, reminder_msg_id = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        [
            {"type": "email_bounce", "message_id": feedback_msg_id},
            {"type": "email_spam", "message_id": reminder_msg_id},
        ],
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        d_r = get_dispatch(fresh, s.id, EmailChannel.REMINDER)
        assert d_f is not None and d_f.status == EmailStatus.BOUNCED
        assert d_r is not None and d_r.status == EmailStatus.COMPLAINT
    finally:
        fresh.close()


def test_event_with_missing_message_id_is_skipped(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")
    s, feedback_msg_id, _ = _seed_signup_with_message_ids(db)

    r = _post_event(
        client,
        [
            {"type": "email_bounce"},
            {"type": "email_bounce", "message_id": feedback_msg_id},
        ],
    )
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.BOUNCED
    finally:
        fresh.close()


def test_does_not_downgrade_already_bounced_dispatch(
    db: Any, client: Any, monkeypatch: Any
) -> None:
    """If the dispatch was retired (or already in another final
    state), a late webhook event must not flip it back. The
    ``status='sent'`` filter on the UPDATE protects this."""
    monkeypatch.setenv("OPKOMST_ALLOW_UNSIGNED_WEBHOOKS", "1")

    e = make_event(db, starts_in=timedelta(hours=24))
    s = make_signup(db, e, email="alice@example.test", feedback="bounced", reminder=False)
    msg_id = "<old@opkomst.nu>"
    d = get_dispatch(db, s.id, EmailChannel.FEEDBACK)
    assert d is not None
    d.message_id = msg_id
    commit(db)

    r = _post_event(client, {"type": "email_spam", "message_id": msg_id})
    assert r.status_code == 204

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, EmailChannel.FEEDBACK)
        # Still bounced — the spam event did not downgrade.
        assert d is not None and d.status == EmailStatus.BOUNCED
    finally:
        fresh.close()
