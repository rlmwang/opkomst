"""State-transition table-test for the email lifecycle.

One row per (start_state, trigger) → (end_state, end_ciphertext).
A regression in any state-changing path (dispatcher, reaper,
channel retirement, post-event purge) breaks exactly one row in
the table, which is faster to localise than a logical-chain test
failure.

The wipe invariant is asserted after every transition: a dispatch
row's own ``encrypted_email`` is set iff its status is PENDING.
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
    EmailDispatch,
    EmailStatus,
    Event,
)
from backend.services import mail_lifecycle


def _set_status(
    signup,  # noqa: ANN001
    channel: EmailChannel,
    status: EmailStatus,
    *,
    message_id: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        d = get_dispatch(db, signup, channel)
        assert d is not None, "dispatch row missing"
        d.status = status
        if message_id is not None:
            d.message_id = message_id
        db.commit()
    finally:
        db.close()


def _read(signup, channel: EmailChannel) -> tuple[EmailStatus | None, bool]:  # noqa: ANN001
    """Return (status, has_ciphertext). status=None means no row.
    has_ciphertext reads the dispatch row's own encrypted_email."""
    db = SessionLocal()
    try:
        d = get_dispatch(db, signup, channel)
        return (d.status if d else None, bool(d and d.encrypted_email is not None))
    finally:
        db.close()


def _check_wipe_invariant() -> None:
    """Per-row property: every non-PENDING dispatch row has its
    own ``encrypted_email`` nulled. No cross-table existence
    check — the address lives on the same row that finalises."""
    db = SessionLocal()
    try:
        for d in db.query(EmailDispatch).all():
            if d.status != EmailStatus.PENDING:
                assert d.encrypted_email is None, (
                    f"invariant broken: {d.channel.value} status={d.status.value} still carries ciphertext"
                )
    finally:
        db.close()


# --- Triggers ----------------------------------------------------------


def _worker_success(signup_id: str) -> None:
    with patch("backend.services.mail_lifecycle.send_with_retry", return_value=True):
        mail_lifecycle.run_once(EmailChannel.REMINDER)


def _worker_failure(signup_id: str) -> None:
    with patch("backend.services.mail_lifecycle.send_with_retry", return_value=False):
        mail_lifecycle.run_once(EmailChannel.REMINDER)


def _retire_reminder(_signup_id: str) -> None:
    db = SessionLocal()
    try:
        ev = db.query(Event).first()
        assert ev is not None
        mail_lifecycle.retire_event_channels(db, event_id=ev.id, channels={EmailChannel.REMINDER})
        db.commit()
    finally:
        db.close()


def _reap_partial(_signup_id: str) -> None:
    db = SessionLocal()
    try:
        mail_lifecycle.reap_partial_sends(db)
    finally:
        db.close()


def _post_event_purge(_signup_id: str) -> None:
    """Push the event ≥7 days into the past, run the reaper.
    Both ``starts_at`` and ``ends_at`` move so the predicate
    fires for both REMINDER (``starts_at <= now``) and FEEDBACK
    (``ends_at <= now - 7d``); the table-test only seeds REMINDER
    rows, so without the ``starts_at`` mutation the reaper would
    skip them."""
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        db.query(Event).update(
            {
                Event.starts_at: now - timedelta(days=14),
                Event.ends_at: now - timedelta(days=14) + timedelta(hours=2),
            }
        )
        db.commit()
    finally:
        db.close()
    mail_lifecycle.reap_expired()


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
    # Start: SENT. Terminal — reaper / retire / worker are no-ops.
    (EmailStatus.SENT, "<m3>", "retire_reminder", EmailStatus.SENT, False),
    (EmailStatus.SENT, "<m4>", "reap_partial", EmailStatus.SENT, False),
    # Worker doesn't pick up SENT rows.
    (EmailStatus.SENT, "<m5>", "worker_success", EmailStatus.SENT, False),
    # Start: FAILED. Terminal — reaper / retire / worker are no-ops.
    (EmailStatus.FAILED, "<m6>", "reap_partial", EmailStatus.FAILED, False),
    (EmailStatus.FAILED, "<m7>", "retire_reminder", EmailStatus.FAILED, False),
    (EmailStatus.FAILED, None, "worker_success", EmailStatus.FAILED, False),
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
    # ``feedback=False`` keeps the table focused on the EmailChannel.REMINDER
    # lifecycle: the wipe semantics only fire when there are no
    # other pending dispatches, so a phantom feedback row would
    # mask every "ciphertext wiped" transition.
    e = make_event(db, starts_in=timedelta(hours=24), feedback_enabled=False)
    s = make_signup(db, e, email="alice@example.test", feedback=False)
    commit(db)

    if start_status != EmailStatus.PENDING or start_msg_id is not None:
        # Move the row off the default PENDING / ciphertext-set
        # state. Null the dispatch's own encrypted_email if the
        # start state is terminal (matches the production
        # invariant: terminal rows have no ciphertext).
        _set_status(s, EmailChannel.REMINDER, start_status, message_id=start_msg_id)
        if start_status != EmailStatus.PENDING:
            fresh = SessionLocal()
            try:
                fresh.query(EmailDispatch).filter(
                    EmailDispatch.event_id == s.event_id,
                    EmailDispatch.channel == EmailChannel.REMINDER,
                ).update({EmailDispatch.encrypted_email: None})
                fresh.commit()
            finally:
                fresh.close()

    _TRIGGERS[trigger](s.id)

    status, has_ciphertext = _read(s, EmailChannel.REMINDER)
    assert status == end_status, f"status: got {status}, expected {end_status}"
    assert has_ciphertext == end_ciphertext, (
        f"ciphertext: got {'set' if has_ciphertext else 'null'}, expected {'set' if end_ciphertext else 'null'}"
    )
    _check_wipe_invariant()
