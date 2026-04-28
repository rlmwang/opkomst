"""Behavioural tests for the generic ``services.email_dispatcher``.

Each behaviour is parametrised over both channels (feedback +
reminder) so the duplication that used to live in two ~230-line
worker test files is gone — the source they tested is gone, the
test parametrisation falls out of that.

The two channels differ only in *when* their window opens (72h
before event start vs. 24h after event end) and in feedback's
extra token mint. Everything else — atomic claim, decrypt failure,
status transitions, parallel safety, ciphertext wipe — is shared.
"""

from datetime import timedelta
from typing import Any

import pytest
from _worker_helpers import commit, get_dispatch, make_event, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, FeedbackToken, Signup
from backend.services import email_dispatcher
from backend.services.email_channels import FEEDBACK, REMINDER, ChannelSpec

# Event timing per channel: when does the window open?
# ``starts_in`` for the event we create in each test.
_TIMING = {
    EmailChannel.REMINDER: {"starts_in": timedelta(hours=24)},
    EmailChannel.FEEDBACK: {
        "starts_in": timedelta(hours=-26),
        "duration": timedelta(hours=1),
    },
}


def _spec(channel: EmailChannel) -> ChannelSpec:
    return REMINDER if channel == EmailChannel.REMINDER else FEEDBACK


def _make_event_in_window(db: Any, channel: EmailChannel, **overrides: Any) -> Any:
    return make_event(db, **{**_TIMING[channel], **overrides})


# A pair of (channel, opposite_channel) tuples for the
# "wipe-when-other-pending" and "wipe-after-other-sent" cases.
_BOTH_CHANNELS = [EmailChannel.REMINDER, EmailChannel.FEEDBACK]


# --- Window gating ---------------------------------------------------


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_fires_when_in_window(channel: EmailChannel, db: Any, fake_email: Any) -> None:
    e = _make_event_in_window(db, channel)
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = email_dispatcher.run_once(_spec(channel))
    assert n == 1
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.test"


def test_reminder_does_not_fire_when_event_far_out(
    db: Any, fake_email: Any
) -> None:
    """4 days out is outside the 72h window."""
    e = make_event(db, starts_in=timedelta(days=4))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_dispatcher.run_once(REMINDER) == 0
    assert fake_email.sent == []


def test_reminder_does_not_fire_for_past_event(db: Any, fake_email: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=-1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_dispatcher.run_once(REMINDER) == 0


def test_feedback_does_not_fire_too_soon(db: Any, fake_email: Any) -> None:
    """Event ended 1h ago — under the 24h cutoff."""
    e = make_event(db, starts_in=timedelta(hours=-2), duration=timedelta(hours=1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_dispatcher.run_once(FEEDBACK) == 0


def test_feedback_does_not_fire_for_future_event(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(days=2))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    assert email_dispatcher.run_once(FEEDBACK) == 0


@pytest.mark.parametrize(
    "channel,toggle_kwarg",
    [
        (EmailChannel.REMINDER, "reminder_enabled"),
        (EmailChannel.FEEDBACK, "questionnaire_enabled"),
    ],
)
def test_does_not_fire_when_event_toggle_off(
    channel: EmailChannel, toggle_kwarg: str, db: Any, fake_email: Any
) -> None:
    """Even if a dispatch row somehow exists with status=pending,
    the worker query is gated on the event's toggle."""
    e = _make_event_in_window(db, channel, **{toggle_kwarg: False})
    # Force-create a pending dispatch despite the toggle being off.
    make_signup(
        db,
        e,
        email="alice@example.test",
        **{channel.value: "pending"},  # type: ignore[arg-type]
    )
    commit(db)

    assert email_dispatcher.run_once(_spec(channel)) == 0


# --- Status transitions ----------------------------------------------


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_marks_sent_and_mints_message_id(
    channel: EmailChannel, db: Any, fake_email: Any
) -> None:
    e = _make_event_in_window(db, channel)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_dispatcher.run_once(_spec(channel))

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, channel)
        assert d is not None
        assert d.status == EmailStatus.SENT
        assert d.message_id is not None
        assert d.sent_at is not None
    finally:
        fresh.close()


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_failed_send_marks_failed_and_clears_message_id(
    channel: EmailChannel, db: Any, fake_email: Any
) -> None:
    e = _make_event_in_window(db, channel)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 999)

    email_dispatcher.run_once(_spec(channel))

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, channel)
        assert d is not None
        assert d.status == EmailStatus.FAILED
        assert d.message_id is None
    finally:
        fresh.close()


def test_reminder_retry_succeeds_on_second_attempt(
    db: Any, fake_email: Any
) -> None:
    e = _make_event_in_window(db, EmailChannel.REMINDER)
    make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 1)

    email_dispatcher.run_once(REMINDER)

    assert len(fake_email.sent) == 1


# --- Feedback-specific token lifecycle -------------------------------


def test_feedback_send_mints_token(db: Any, fake_email: Any) -> None:
    e = _make_event_in_window(db, EmailChannel.FEEDBACK)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_dispatcher.run_once(FEEDBACK)

    fresh = SessionLocal()
    try:
        tokens = (
            fresh.query(FeedbackToken)
            .filter(FeedbackToken.signup_id == s.id)
            .all()
        )
        assert len(tokens) == 1
    finally:
        fresh.close()


def test_feedback_failed_send_drops_token(db: Any, fake_email: Any) -> None:
    e = _make_event_in_window(db, EmailChannel.FEEDBACK)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 999)

    email_dispatcher.run_once(FEEDBACK)

    fresh = SessionLocal()
    try:
        tokens = (
            fresh.query(FeedbackToken)
            .filter(FeedbackToken.signup_id == s.id)
            .all()
        )
        # No point keeping a redeemable link for an email that
        # never went out.
        assert tokens == []
    finally:
        fresh.close()


# --- Lifecycle / wipe ------------------------------------------------


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_done_wipes_when_no_other_pending(
    channel: EmailChannel, db: Any, fake_email: Any
) -> None:
    """Single-channel event: ciphertext wipes after the send."""
    other_off = {
        EmailChannel.REMINDER: {"questionnaire_enabled": False},
        EmailChannel.FEEDBACK: {"reminder_enabled": False},
    }[channel]
    e = _make_event_in_window(db, channel, **other_off)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_dispatcher.run_once(_spec(channel))

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None
    finally:
        fresh.close()


@pytest.mark.parametrize(
    "channel,other_channel",
    [
        (EmailChannel.REMINDER, EmailChannel.FEEDBACK),
        (EmailChannel.FEEDBACK, EmailChannel.REMINDER),
    ],
)
def test_keeps_ciphertext_when_other_channel_pending(
    channel: EmailChannel,
    other_channel: EmailChannel,
    db: Any,
    fake_email: Any,
) -> None:
    """When another channel still has a pending dispatch,
    ciphertext must stay so its worker can decrypt later."""
    e = _make_event_in_window(db, channel)
    # Default: both channels pending (event toggles default to on).
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    email_dispatcher.run_once(_spec(channel))

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is not None
        # The just-processed channel is now sent.
        d_processed = get_dispatch(fresh, s.id, channel)
        assert d_processed is not None
        assert d_processed.status == EmailStatus.SENT
        # The other channel is still pending.
        d_other = get_dispatch(fresh, s.id, other_channel)
        assert d_other is not None
        assert d_other.status == EmailStatus.PENDING
    finally:
        fresh.close()


# --- Decrypt failure -------------------------------------------------


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_decrypt_failure_flips_to_failed_once(
    channel: EmailChannel, db: Any, fake_email: Any
) -> None:
    """Phase 2.2: corrupt ciphertext is unrecoverable, so the
    first decrypt failure flips the dispatch to ``failed`` and
    clears the message_id. The next sweep won't re-process."""
    e = _make_event_in_window(db, channel)
    s = make_signup(db, e, email="alice@example.test")
    s.encrypted_email = b"not-real-ciphertext"
    db.add(s)
    commit(db)

    email_dispatcher.run_once(_spec(channel))

    fresh = SessionLocal()
    try:
        d = get_dispatch(fresh, s.id, channel)
        assert d is not None
        assert d.status == EmailStatus.FAILED
        assert d.message_id is None
    finally:
        fresh.close()
    assert fake_email.sent == []

    # Subsequent sweep finds nothing.
    assert email_dispatcher.run_once(_spec(channel)) == 0


# --- Conditional UPDATE / parallel safety ----------------------------


@pytest.mark.parametrize("channel", _BOTH_CHANNELS)
def test_conditional_update_does_not_stomp_existing_status(
    channel: EmailChannel, db: Any, fake_email: Any
) -> None:
    """Phase 1.2 invariant: if a parallel worker (or toggle-off
    cleanup) flipped the dispatch out of ``pending`` while this
    worker was sending, our final UPDATE must NOT re-stomp it.

    Simulate by:
      1. Fetching the dispatch row in session A.
      2. From session B, deleting it (toggle-off cleanup).
      3. Calling ``_process_one`` from session A.

    The atomic claim that pre-mints message_id is filtered on
    ``status='pending' AND message_id IS NULL``; session B's
    delete moved the row out from under us, so the claim returns
    0 rows and the worker bails — no email goes out.
    """
    e = _make_event_in_window(db, channel)
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        d_a = get_dispatch(session_a, s.id, channel)
        signup_a = session_a.query(Signup).filter(Signup.id == s.id).first()
        event_a = session_a.query(type(e)).filter_by(id=e.id).first()
        assert d_a is not None and signup_a is not None and event_a is not None

        # Race: session B deletes the dispatch.
        d_b = get_dispatch(session_b, s.id, channel)
        assert d_b is not None
        session_b.delete(d_b)
        session_b.commit()

        # Session A's identity map still has the stale row, but
        # the conditional UPDATE in _process_one runs against DB
        # truth and matches zero rows.
        email_dispatcher._process_one(session_a, _spec(channel), signup_a, event_a, d_a)
        session_a.commit()
    finally:
        session_a.close()
        session_b.close()

    # No email sent — claim never succeeded.
    assert fake_email.sent == []
