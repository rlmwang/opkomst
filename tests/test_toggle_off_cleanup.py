"""Tests for ``mail_lifecycle.retire_event_channels``.

When an organiser flips an email toggle off in the event-edit
form, signups still waiting on that channel must (a) lose their
pending dispatch row and (b) lose their ciphertext if no other
dispatch row remains — privacy doesn't wait for the operator to
remember to come back later.

In-flight sends (``message_id IS NOT NULL``) are deliberately
excluded so a toggle-off can never stomp a worker mid-SMTP-call.
"""

from datetime import timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import get_dispatch, has_any_ciphertext, make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, EmailStatus, Signup
from backend.services import mail_lifecycle


def test_disabling_reminder_retires_pending_reminder(db: Any) -> None:
    """Both toggles on; signup pending on both. Reminder gets
    retired → dispatch deleted, but ciphertext stays because
    feedback is still pending."""
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    fresh = SessionLocal()
    try:
        mail_lifecycle.retire_event_channels(
            fresh,
            event_id=e.id,
            channels={EmailChannel.REMINDER},
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        assert get_dispatch(fresh, s, EmailChannel.REMINDER) is None
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert has_any_ciphertext(fresh, row)
    finally:
        fresh.close()


def test_disabling_both_channels_wipes_ciphertext(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

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
        assert get_dispatch(fresh, s, EmailChannel.REMINDER) is None
        assert get_dispatch(fresh, s, EmailChannel.FEEDBACK) is None
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert not has_any_ciphertext(fresh, row)
    finally:
        fresh.close()


def test_disabling_one_when_other_already_sent_wipes(db: Any) -> None:
    """Reminder already sent; organiser disables feedback. The
    'still pending' check sees nothing pending and wipes."""
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(
        db,
        e,
        email="alice@example.test",
        reminder="sent",
    )
    commit(db)

    fresh = SessionLocal()
    try:
        mail_lifecycle.retire_event_channels(
            fresh,
            event_id=e.id,
            channels={EmailChannel.FEEDBACK},
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        assert get_dispatch(fresh, s, EmailChannel.FEEDBACK) is None
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d_r is not None and d_r.status == EmailStatus.SENT
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert not has_any_ciphertext(fresh, row)
    finally:
        fresh.close()


def test_disabling_skips_rows_currently_mid_send(db: Any) -> None:
    """Phase 3 review fix: ``retire_event_channels`` must NOT
    delete a dispatch whose worker has already pre-minted a
    message_id. Excluded by the ``message_id IS NULL`` filter so
    the worker's SMTP send finalises legitimately.
    """
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.com")
    # Mid-send: pre-minted message_id, status still pending.
    d_f = get_dispatch(db, s, EmailChannel.FEEDBACK)
    d_r = get_dispatch(db, s, EmailChannel.REMINDER)
    assert d_f is not None and d_r is not None
    d_f.message_id = "<claimed@opkomst.nu>"
    d_r.message_id = "<claimed@opkomst.nu>"
    commit(db)

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
        # Both dispatch rows still present, still pending.
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
        assert d_r is not None and d_r.status == EmailStatus.PENDING
        # Ciphertext also kept — the wipe predicate sees a pending
        # dispatch and bails.
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert has_any_ciphertext(fresh, row)
    finally:
        fresh.close()


def test_empty_channel_set_is_noop(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    fresh = SessionLocal()
    try:
        mail_lifecycle.retire_event_channels(
            fresh,
            event_id=e.id,
            channels=set(),
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        d_f = get_dispatch(fresh, s, EmailChannel.FEEDBACK)
        d_r = get_dispatch(fresh, s, EmailChannel.REMINDER)
        assert d_f is not None and d_f.status == EmailStatus.PENDING
        assert d_r is not None and d_r.status == EmailStatus.PENDING
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert has_any_ciphertext(fresh, row)
    finally:
        fresh.close()
