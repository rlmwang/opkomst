"""Tests for ``routers.events._retire_disabled_channels``.

When an organiser flips an email toggle off in the event-edit
form, signups still waiting on that channel must (a) move from
``pending`` to ``not_applicable`` and (b) lose their ciphertext
if the *other* channel is also done — privacy doesn't wait for
the operator to remember to come back later.
"""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import Signup
from backend.routers.events import _retire_disabled_channels


def test_disabling_reminder_retires_pending_reminders(db: Any) -> None:
    """Both toggles on; signup pending on both. Reminder gets
    retired → status flips to not_applicable, but ciphertext
    stays because feedback is still pending."""
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")  # both pending
    commit(db)

    fresh = SessionLocal()
    try:
        _retire_disabled_channels(
            fresh,
            event_entity_id=e.entity_id,
            questionnaire_disabled=False,
            reminder_disabled=True,
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.reminder_email_status == "not_applicable"
        assert row.feedback_email_status == "pending"
        assert row.encrypted_email is not None  # feedback still pending
    finally:
        fresh.close()


def test_disabling_both_channels_wipes_ciphertext(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

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

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "not_applicable"
        assert row.reminder_email_status == "not_applicable"
        assert row.encrypted_email is None  # nothing left to wait on
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
        reminder_status="sent",  # already done
    )
    commit(db)

    fresh = SessionLocal()
    try:
        _retire_disabled_channels(
            fresh,
            event_entity_id=e.entity_id,
            questionnaire_disabled=True,
            reminder_disabled=False,
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "not_applicable"
        assert row.encrypted_email is None
    finally:
        fresh.close()


def test_disabling_skips_rows_currently_mid_send(db: Any) -> None:
    """Phase 3 review fix: ``_retire_disabled_channels`` must
    NOT flip a row whose worker has already pre-minted a
    message_id (Phase 2.1's claim). The worker's SMTP send is
    in flight; if we retire the row to ``not_applicable`` while
    that's happening, the email goes out but the row says it
    didn't.

    Simulate by setting message_id on a still-pending row
    (mimicking a worker that just claimed it) and asserting
    the retire helper leaves the row alone."""
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.com")
    s.feedback_message_id = "<claimed@opkomst.nu>"
    s.reminder_message_id = "<claimed@opkomst.nu>"
    db.add(s)
    commit(db)

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

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        # The ``message_id IS NULL`` filter excluded this row from
        # the retire UPDATEs — its status stays ``pending`` and
        # the worker can finish its send legitimately.
        assert row.feedback_email_status == "pending"
        assert row.reminder_email_status == "pending"
        # Ciphertext is also kept — the wipe filter requires both
        # statuses to be != pending.
        assert row.encrypted_email is not None
    finally:
        fresh.close()


def test_disabling_with_neither_flag_set_is_noop(db: Any) -> None:
    """Defensive: if both flags are False the helper returns
    early — the row state must be untouched."""
    e = make_event(db, starts_in=timedelta(days=4))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    fresh = SessionLocal()
    try:
        _retire_disabled_channels(
            fresh,
            event_entity_id=e.entity_id,
            questionnaire_disabled=False,
            reminder_disabled=False,
        )
        fresh.commit()
    finally:
        fresh.close()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "pending"
        assert row.reminder_email_status == "pending"
        assert row.encrypted_email is not None
    finally:
        fresh.close()
