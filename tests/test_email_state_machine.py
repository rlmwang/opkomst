"""State-transition table-test for the email lifecycle.

A dispatch row is outstanding work, so there are three states, not
five: ``queued`` (a row nobody has claimed), ``claimed`` (a row whose
message_id was minted, meaning a worker was mid-send), and ``gone``
(no row, because the send finished one way or the other).

One row per (start_state, trigger) → (end_state, sent, failed). A
regression in any state-changing path — dispatcher, reaper, channel
retirement, post-event purge — breaks exactly one row in the table,
which is faster to localise than a logical-chain failure.

The wipe invariant is asserted after every transition, and it is now a
statement about existence rather than about a column: a row that is
still here is work still owed, and every row that leaves takes its
address with it.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, make_signup, send_counts

from backend.database import SessionLocal
from backend.models import (
    EmailChannel,
    EmailDispatch,
    Event,
    Occurrence,
)
from backend.services import mail_lifecycle

QUEUED = "queued"
CLAIMED = "claimed"
GONE = "gone"


def _put_in_state(signup, channel: EmailChannel, state: str) -> None:  # noqa: ANN001
    """Move the seeded row into the start state under test."""
    db = SessionLocal()
    try:
        d = get_dispatch(db, signup, channel)
        assert d is not None, "dispatch row missing"
        if state == GONE:
            db.delete(d)
        elif state == CLAIMED:
            d.message_id = "<mid-send>"
        db.commit()
    finally:
        db.close()


def _read(signup, channel: EmailChannel) -> str:  # noqa: ANN001
    """The row's state: gone, claimed, or queued."""
    db = SessionLocal()
    try:
        d = get_dispatch(db, signup, channel)
        if d is None:
            return GONE
        return CLAIMED if d.message_id is not None else QUEUED
    finally:
        db.close()


def _check_wipe_invariant() -> None:
    """Existence is the invariant. A dispatch row is work still owed,
    and it is the only place an address lives; anything finished has no
    row, so there is nothing left to carry an address."""
    db = SessionLocal()
    try:
        for d in db.query(EmailDispatch).all():
            assert d.encrypted_email is not None or d.message_id is not None, (
                f"invariant broken: {d.channel.value} row is owed but carries no address"
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
    """Push the occurrence ≥7 days into the past, run the reaper.
    Both ``starts_at`` and ``ends_at`` move so the predicate
    fires for both REMINDER (``starts_at <= now``) and FEEDBACK
    (``ends_at <= now - 7d``); the table-test only seeds REMINDER
    rows, so without the ``starts_at`` mutation the reaper would
    skip them. Occurrence datetimes are naive wall-clock, so use
    a naive ``now`` for the shift."""
    db = SessionLocal()
    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        db.query(Occurrence).update(
            {
                Occurrence.starts_at: now - timedelta(days=14),
                Occurrence.ends_at: now - timedelta(days=14) + timedelta(hours=2),
            }
        )
        db.commit()
    finally:
        db.close()
    mail_lifecycle.reap_expired()


# --- Table -------------------------------------------------------------
#
# Each row: (start_state, trigger_name, expected_end_state, expected
# (sent, failed) counted by that trigger).
#
# ``trigger_name`` indexes ``_TRIGGERS`` below. A ``gone`` start state
# is a send that already finished: the triggers must leave it alone and
# count nothing, because there is nothing left to act on.

_TRIGGERS = {
    "worker_success": _worker_success,
    "worker_failure": _worker_failure,
    "retire_reminder": _retire_reminder,
    "reap_partial": _reap_partial,
    "post_event_purge": _post_event_purge,
}

_TABLE: list[tuple[str, str, str, tuple[int, int]]] = [
    # Queued work, and the worker drives it to done either way.
    (QUEUED, "worker_success", GONE, (1, 0)),
    (QUEUED, "worker_failure", GONE, (0, 1)),
    # A claimed row is a worker that never came back: the reaper counts
    # the failure and deletes it. An unclaimed one is left alone.
    (CLAIMED, "reap_partial", GONE, (0, 1)),
    (QUEUED, "reap_partial", QUEUED, (0, 0)),
    # Retiring a channel drops work nobody asked for any more. It is not
    # a failed send, so nothing is counted. A claimed row is mid-send and
    # left to finish on its own.
    (QUEUED, "retire_reminder", GONE, (0, 0)),
    (CLAIMED, "retire_reminder", CLAIMED, (0, 0)),
    # The window closed on work that never happened.
    (QUEUED, "post_event_purge", GONE, (0, 1)),
    (CLAIMED, "post_event_purge", GONE, (0, 1)),
    # Already finished: every trigger is a no-op, and none of them
    # invents a second outcome for a send that already had one.
    (GONE, "worker_success", GONE, (0, 0)),
    (GONE, "worker_failure", GONE, (0, 0)),
    (GONE, "reap_partial", GONE, (0, 0)),
    (GONE, "retire_reminder", GONE, (0, 0)),
    (GONE, "post_event_purge", GONE, (0, 0)),
]


@pytest.mark.parametrize(
    "start_state,trigger,end_state,expected_counts",
    _TABLE,
)
def test_state_transition_table(
    db: Any,
    fake_email: Any,
    start_state: str,
    trigger: str,
    end_state: str,
    expected_counts: tuple[int, int],
) -> None:
    # ``feedback=False`` keeps the table focused on the REMINDER
    # lifecycle: a phantom feedback row would keep the booking's
    # ciphertext alive and mask every transition being asserted.
    e = make_event(db, starts_in=timedelta(hours=24), feedback_enabled=False)
    s = make_signup(db, e, email="alice@example.test", feedback=False)
    commit(db)

    _put_in_state(s, EmailChannel.REMINDER, start_state)

    _TRIGGERS[trigger](s.id)

    assert _read(s, EmailChannel.REMINDER) == end_state, f"state: expected {end_state}"
    fresh = SessionLocal()
    try:
        assert send_counts(fresh, s, EmailChannel.REMINDER) == expected_counts
    finally:
        fresh.close()
    _check_wipe_invariant()
