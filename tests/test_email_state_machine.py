"""State-transition table-test for the email lifecycle.

One row per (start_state, trigger) → (end_state, end_ciphertext).
A regression in any state-changing path (dispatcher, webhook,
reaper, channel retirement, post-event purge) breaks exactly one
row in the table, which is faster to localise than a logical-
chain test failure.

The wipe invariant is asserted after every transition:
``encrypted_email IS NULL`` ⇔ no PENDING dispatch row.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, make_signup

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailStatus,
    Event,
    Signup,
    SignupEmailDispatch,
)
from backend.services import email_dispatcher, email_reaper
from backend.services.email_channels import REMINDER


def _set_status(
    signup_id: str,
    channel: EmailChannel,
    status: EmailStatus,
    *,
    message_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        d = get_dispatch(db, signup_id, channel)
        assert d is not None, "dispatch row missing"
        d.status = status
        if message_id is not None:
            d.message_id = message_id
        db.commit()
    finally:
        db.close()


def _read(signup_id: str, channel: EmailChannel) -> tuple[EmailStatus | None, bool]:
    """Return (status, has_ciphertext). status=None means no row."""
    db = SessionLocal()
    try:
        s = db.query(Signup).filter(Signup.id == signup_id).first()
        assert s is not None
        d = get_dispatch(db, signup_id, channel)
        return (d.status if d else None, s.encrypted_email is not None)
    finally:
        db.close()


def _check_wipe_invariant(signup_id: str) -> None:
    db = SessionLocal()
    try:
        s = db.query(Signup).filter(Signup.id == signup_id).one()
        pending = (
            db.query(SignupEmailDispatch)
            .filter(
                SignupEmailDispatch.signup_id == signup_id,
                SignupEmailDispatch.status == EmailStatus.PENDING,
            )
            .count()
        )
        assert (s.encrypted_email is None) == (pending == 0), (
            f"invariant: encrypted_email={'set' if s.encrypted_email else 'null'} "
            f"pending={pending}"
        )
    finally:
        db.close()


# --- Triggers ----------------------------------------------------------


def _worker_success(signup_id: str) -> None:
    with patch(
        "backend.services.email_dispatcher.send_with_retry", return_value=True
    ):
        email_dispatcher.run_once(REMINDER)


def _worker_failure(signup_id: str) -> None:
    with patch(
        "backend.services.email_dispatcher.send_with_retry", return_value=False
    ):
        email_dispatcher.run_once(REMINDER)


def _webhook(message_id: str, event_type: str, client) -> None:  # noqa: ANN001
    """Fire a webhook event. Signature verification is bypassed
    when ``SCALEWAY_WEBHOOK_SECRET`` is unset (returns 503 if set
    without signature). Tests run with no secret configured."""
    r = client.post(
        "/api/v1/webhooks/scaleway-email",
        json={"type": event_type, "message_id": message_id},
    )
    assert r.status_code in (204, 503), r.text


def _retire_reminder(_signup_id: str) -> None:
    db = SessionLocal()
    try:
        ev = db.query(Event).filter(Event.valid_until.is_(None)).first()
        assert ev is not None
        email_reaper.retire_event_channels(
            db, event_entity_id=ev.entity_id, channels={EmailChannel.REMINDER}
        )
        db.commit()
    finally:
        db.close()


def _reap_partial(_signup_id: str) -> None:
    db = SessionLocal()
    try:
        email_reaper.reap_partial_sends(db)
    finally:
        db.close()


def _post_event_purge(_signup_id: str) -> None:
    """Push the event ≥7 days into the past, run the purge."""
    db = SessionLocal()
    try:
        db.query(Event).filter(Event.valid_until.is_(None)).update(
            {Event.ends_at: datetime.now(UTC) - timedelta(days=14)}
        )
        db.commit()
    finally:
        db.close()
    email_reaper.purge_post_event_emails()


# --- Table -------------------------------------------------------------
#
# Each row: (start_status, start_message_id, trigger_name,
#           expected_end_status_or_None, expected_end_ciphertext)
#
# ``trigger_name`` indexes ``_TRIGGERS`` below. ``message_id=None``
# means leave it null; a string sets it explicitly. ``end_status=
# None`` means "row no longer exists" (channel retired). The
# ciphertext column is the post-trigger expected value.

_TRIGGERS = {
    "worker_success": _worker_success,
    "worker_failure": _worker_failure,
    "retire_reminder": _retire_reminder,
    "reap_partial": _reap_partial,
    "post_event_purge": _post_event_purge,
}

_TABLE: list[tuple[EmailStatus, str | None, str, EmailStatus | None, bool]] = [
    # Start: PENDING. Worker drives.
    (EmailStatus.PENDING, None, "worker_success", EmailStatus.SENT, False),
    (EmailStatus.PENDING, None, "worker_failure", EmailStatus.FAILED, False),
    # Reaper paths.
    (EmailStatus.PENDING, "<m1>", "reap_partial", EmailStatus.FAILED, False),
    (EmailStatus.PENDING, None, "reap_partial", EmailStatus.PENDING, True),
    # Channel retirement deletes the pending row.
    (EmailStatus.PENDING, None, "retire_reminder", None, False),
    (EmailStatus.PENDING, "<m2>", "retire_reminder", EmailStatus.PENDING, True),
    # Post-event purge finalises orphaned pending rows.
    (
        EmailStatus.PENDING,
        None,
        "post_event_purge",
        EmailStatus.FAILED,
        False,
    ),
    # Start: SENT. Reaper / retire are no-ops; only webhook flips it.
    (EmailStatus.SENT, "<m3>", "retire_reminder", EmailStatus.SENT, False),
    (EmailStatus.SENT, "<m4>", "reap_partial", EmailStatus.SENT, False),
    # Worker doesn't pick up SENT rows.
    (EmailStatus.SENT, "<m5>", "worker_success", EmailStatus.SENT, False),
    # Start: FAILED. Worker doesn't retry; reaper / retire / webhook
    # late events leave it alone.
    (EmailStatus.FAILED, "<m6>", "reap_partial", EmailStatus.FAILED, False),
    (EmailStatus.FAILED, "<m7>", "retire_reminder", EmailStatus.FAILED, False),
    (EmailStatus.FAILED, None, "worker_success", EmailStatus.FAILED, False),
    # Start: BOUNCED. Terminal — nothing flips it back.
    (EmailStatus.BOUNCED, "<m8>", "reap_partial", EmailStatus.BOUNCED, False),
    (
        EmailStatus.BOUNCED,
        "<m9>",
        "retire_reminder",
        EmailStatus.BOUNCED,
        False,
    ),
    (
        EmailStatus.BOUNCED,
        "<m10>",
        "post_event_purge",
        EmailStatus.BOUNCED,
        False,
    ),
    # Start: COMPLAINT. Same terminal semantics.
    (
        EmailStatus.COMPLAINT,
        "<m11>",
        "reap_partial",
        EmailStatus.COMPLAINT,
        False,
    ),
    (
        EmailStatus.COMPLAINT,
        "<m12>",
        "retire_reminder",
        EmailStatus.COMPLAINT,
        False,
    ),
    # post_event_purge wipes ciphertext but doesn't disturb terminal
    # statuses — the orphaned-PENDING transition only fires on PENDING.
    (
        EmailStatus.SENT,
        "<m13>",
        "post_event_purge",
        EmailStatus.SENT,
        False,
    ),
    (
        EmailStatus.FAILED,
        "<m14>",
        "post_event_purge",
        EmailStatus.FAILED,
        False,
    ),
]


@pytest.mark.parametrize(
    "start_status,start_msg_id,trigger,end_status,end_ciphertext",
    _TABLE,
)
def test_state_transition_table(
    db: Any,
    fake_email: Any,
    start_status: EmailStatus,
    start_msg_id: str | None,
    trigger: str,
    end_status: EmailStatus | None,
    end_ciphertext: bool,
) -> None:
    # ``feedback=False`` keeps the table focused on the REMINDER
    # lifecycle: the wipe semantics only fire when there are no
    # other pending dispatches, so a phantom feedback row would
    # mask every "ciphertext wiped" transition.
    e = make_event(
        db, starts_in=timedelta(hours=24), questionnaire_enabled=False
    )
    s = make_signup(db, e, email="alice@example.test", feedback=False)
    commit(db)

    if start_status != EmailStatus.PENDING or start_msg_id is not None:
        # Move the row off the default PENDING / null state. Wipe
        # ciphertext too if the start state implies the worker has
        # already finalised — the conftest defaults to ciphertext
        # present, dispatch row PENDING.
        _set_status(s.id, EmailChannel.REMINDER, start_status, message_id=start_msg_id)
        if start_status != EmailStatus.PENDING:
            fresh = SessionLocal()
            try:
                fresh.query(Signup).filter(Signup.id == s.id).update(
                    {Signup.encrypted_email: None}
                )
                fresh.commit()
            finally:
                fresh.close()

    _TRIGGERS[trigger](s.id)

    status, has_ciphertext = _read(s.id, EmailChannel.REMINDER)
    assert status == end_status, f"status: got {status}, expected {end_status}"
    assert has_ciphertext == end_ciphertext, (
        f"ciphertext: got {'set' if has_ciphertext else 'null'}, "
        f"expected {'set' if end_ciphertext else 'null'}"
    )
    _check_wipe_invariant(s.id)
