"""Behavioural tests for ``services.feedback_worker``."""

from datetime import timedelta
from typing import Any

from _worker_helpers import commit, make_event, make_signup

from backend.database import SessionLocal
from backend.models import FeedbackToken, Signup
from backend.services import feedback_worker

# --- Window gating ---------------------------------------------------


def test_feedback_fires_24h_after_event_ends(db: Any, fake_email: Any) -> None:
    """Event ended 25h ago, signup pending, questionnaire on → fires."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = feedback_worker.run_once()
    assert n == 1
    assert len(fake_email.sent) == 1
    assert fake_email.sent[0].to == "alice@example.test"


def test_feedback_does_not_fire_too_soon(db: Any, fake_email: Any) -> None:
    """Event ended 1h ago — under the 24h cutoff."""
    e = make_event(db, starts_in=timedelta(hours=-2), duration=timedelta(hours=1))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = feedback_worker.run_once()
    assert n == 0
    assert fake_email.sent == []


def test_feedback_does_not_fire_when_questionnaire_off(
    db: Any, fake_email: Any
) -> None:
    e = make_event(
        db,
        starts_in=timedelta(hours=-26),
        duration=timedelta(hours=1),
        questionnaire_enabled=False,
    )
    make_signup(
        db,
        e,
        email="alice@example.test",
        feedback_status="pending",  # force pending despite toggle off
    )
    commit(db)

    n = feedback_worker.run_once()
    assert n == 0


def test_feedback_does_not_fire_for_future_event(
    db: Any, fake_email: Any
) -> None:
    """Event hasn't happened yet — no feedback to ask about."""
    e = make_event(db, starts_in=timedelta(days=2))
    make_signup(db, e, email="alice@example.test")
    commit(db)

    n = feedback_worker.run_once()
    assert n == 0


# --- Status transitions ----------------------------------------------


def test_feedback_marks_sent_and_mints_message_id(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "sent"
        assert row.feedback_message_id is not None
        # FeedbackToken minted for the in-email link.
        tokens = fresh.query(FeedbackToken).filter(FeedbackToken.signup_id == s.id).all()
        assert len(tokens) == 1
    finally:
        fresh.close()


def test_feedback_failed_send_drops_token_and_marks_failed(
    db: Any, fake_email: Any
) -> None:
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    commit(db)
    fake_email.fail_n_times("alice@example.test", 999)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "failed"
        assert row.feedback_message_id is None
        # Token was dropped — no point keeping a redeemable link
        # for an email that never went out.
        tokens = fresh.query(FeedbackToken).filter(FeedbackToken.signup_id == s.id).all()
        assert tokens == []
    finally:
        fresh.close()


# --- Lifecycle / wipe ------------------------------------------------


def test_feedback_done_wipes_when_no_other_pending(
    db: Any, fake_email: Any
) -> None:
    """Feedback-only event: wipe ciphertext after the feedback send."""
    e = make_event(
        db,
        starts_in=timedelta(hours=-26),
        duration=timedelta(hours=1),
        reminder_enabled=False,
    )
    s = make_signup(db, e, email="alice@example.test")
    commit(db)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.encrypted_email is None
    finally:
        fresh.close()


def test_feedback_done_wipes_after_reminder_already_sent(
    db: Any, fake_email: Any
) -> None:
    """Both channels were on; reminder already fired (state =
    ``sent``); now feedback fires last → wipe."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(
        db,
        e,
        email="alice@example.test",
        reminder_status="sent",  # reminder already done
    )
    commit(db)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "sent"
        assert row.encrypted_email is None  # both channels done → wipe
    finally:
        fresh.close()


def test_feedback_keeps_ciphertext_if_reminder_still_pending(
    db: Any, fake_email: Any
) -> None:
    """Edge case: reminder hasn't fired yet (somehow a feedback
    fires first). Ciphertext must stay so the reminder worker can
    still decrypt."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")  # both pending
    commit(db)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "sent"
        assert row.reminder_email_status == "pending"
        assert row.encrypted_email is not None
    finally:
        fresh.close()


# --- Conditional UPDATE / parallel safety ----------------------------


def test_feedback_decrypt_failure_flips_to_failed_once(
    db: Any, fake_email: Any
) -> None:
    """Phase 2.2 mirror of the reminder-side test: corrupt
    ciphertext is unrecoverable, so the first decrypt failure
    flips status to ``failed`` and clears the message_id. Next
    sweep won't pick it up."""
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")
    s.encrypted_email = b"not-real-ciphertext"
    db.add(s)
    commit(db)

    feedback_worker.run_once()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        assert row.feedback_email_status == "failed"
        assert row.feedback_message_id is None
    finally:
        fresh.close()
    assert fake_email.sent == []

    n = feedback_worker.run_once()
    assert n == 0


def test_feedback_conditional_update_does_not_stomp_existing_status(
    db: Any, fake_email: Any
) -> None:
    """Phase 1.2 invariant: if a parallel worker (or toggle-off
    cleanup) flipped the status out of ``pending`` while *this*
    worker was sending, our final UPDATE must NOT re-stomp it.

    We simulate the race by:
      1. Fetching the row in session A (status still ``pending``).
      2. From session B, committing a status flip to
         ``not_applicable``.
      3. Calling ``_process_one`` from session A.

    Session A's identity map still holds the stale ``pending``
    state, but ``_process_one``'s WHERE-clause UPDATE matches
    against DB truth, sees ``not_applicable``, and no-ops.
    """
    e = make_event(db, starts_in=timedelta(hours=-26), duration=timedelta(hours=1))
    s = make_signup(db, e, email="alice@example.test")  # both pending
    commit(db)

    session_a = SessionLocal()
    session_b = SessionLocal()
    try:
        row_a = session_a.query(Signup).filter(Signup.id == s.id).first()
        event_a = session_a.query(type(e)).filter_by(id=e.id).first()
        assert row_a is not None
        assert event_a is not None

        # Race: another session flips the status before A's
        # _process_one finishes.
        session_b.query(Signup).filter(Signup.id == s.id).update(
            {Signup.feedback_email_status: "not_applicable"},
            synchronize_session=False,
        )
        session_b.commit()

        # Session A processes the row. Email goes out (Phase 2.1
        # closes that gap); the question we're asserting here is
        # whether session A's UPDATE stomps the not_applicable.
        feedback_worker._process_one(session_a, row_a, event_a)
        session_a.commit()
    finally:
        session_a.close()
        session_b.close()

    fresh = SessionLocal()
    try:
        row = fresh.query(Signup).filter(Signup.id == s.id).first()
        assert row is not None
        # Phase 2.1's atomic claim caught the race: the
        # conditional UPDATE that pre-mints the message_id is
        # filtered on ``status == 'pending' AND message_id IS
        # NULL``. session_b's flip made status non-pending, so
        # the claim returned 0 rows and the worker bailed without
        # sending — and without minting a message_id. The row's
        # final state matches what session_b wrote.
        assert row.feedback_email_status == "not_applicable"
        assert row.feedback_message_id is None
    finally:
        fresh.close()
