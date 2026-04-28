"""Generic email-channel worker.

Runs hourly per channel via APScheduler (wired in
``backend/worker.py``). Replaces the two ~230-line
``feedback_worker.py`` / ``reminder_worker.py`` modules —
their entire shape was identical except for column names,
template names, and time-window predicates, all of which now
live in a ``ChannelSpec``.

Lifecycle of one row::

    [absent]                     # no dispatch yet
       |
       | (signup creates the row at status=pending)
       v
    [pending]
       |
       | (worker pre-mints message_id + commits — atomic claim)
       v
    [pending, message_id set]    # crash here ⇒ reaper flips to failed
       |
       | (SMTP success / failure-after-retry)
       v
    [sent | failed]
       |
       | (Scaleway webhook may transition sent → bounced/complaint)
       v
    [bounced | complaint]

Privacy invariant: the ciphertext is wiped whenever no
``SignupEmailDispatch`` row with status='pending' refers to the
signup. Single SQL existence check, no per-channel logic.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import EmailStatus, Event, Signup, SignupEmailDispatch
from . import encryption
from .email import (
    email_batch_size,
    emit_metric,
    new_message_id,
    send_with_retry,
)

if TYPE_CHECKING:
    from .email_channels import ChannelSpec

logger = structlog.get_logger()


def _wipe_ciphertext_if_done(db: Session, signup_id: str) -> None:
    """DB-side conditional: NULL the ciphertext iff no pending
    dispatch refers to this signup. Single source of truth for
    the privacy invariant; replaces the per-channel
    ``WHERE feedback_status != 'pending' AND reminder_status !=
    'pending'`` predicate the previous design needed."""
    pending_exists = (
        db.query(SignupEmailDispatch.id)
        .filter(
            SignupEmailDispatch.signup_id == signup_id,
            SignupEmailDispatch.status == EmailStatus.PENDING,
        )
        .exists()
    )
    db.query(Signup).filter(
        Signup.id == signup_id,
        ~pending_exists,
    ).update({Signup.encrypted_email: None}, synchronize_session=False)


def _process_one(
    db: Session,
    spec: "ChannelSpec",
    signup: Signup,
    event: Event,
    dispatch: SignupEmailDispatch,
) -> None:
    """Process one dispatch through its lifecycle. Mirrors the
    old ``feedback_worker._process_one`` / ``reminder_worker._process_one``
    pair — same atomic-claim, decrypt-or-fail, send, finalise
    structure, but parameterised over ``spec``."""

    # Step 1 — atomic claim. Set message_id only when the row is
    # still pending AND no message_id has been minted yet. Two
    # parallel workers fighting for the same row will only have
    # one win; the loser's claim returns 0 rows, we bail.
    message_id = new_message_id()
    claimed = (
        db.query(SignupEmailDispatch)
        .filter(
            SignupEmailDispatch.id == dispatch.id,
            SignupEmailDispatch.status == EmailStatus.PENDING,
            SignupEmailDispatch.message_id.is_(None),
        )
        .update(
            {SignupEmailDispatch.message_id: message_id},
            synchronize_session=False,
        )
    )
    db.commit()
    if claimed == 0:
        logger.info(
            "dispatch_skipped_already_claimed",
            channel=spec.channel.value,
            signup_id=signup.id,
        )
        return

    # Step 2 — decrypt. Failures are unrecoverable.
    try:
        plaintext = encryption.decrypt(signup.encrypted_email or b"")
    except Exception:
        logger.exception(
            "dispatch_decrypt_failed",
            channel=spec.channel.value,
            signup_id=signup.id,
        )
        _finalise(db, spec, signup, dispatch, sent=False, message_id=None, hook_state={})
        return

    # Step 3 — per-channel pre-send hook (e.g. feedback's token mint)
    # then send.
    hook_state: dict[str, Any] = {}
    if spec.on_pre_send is not None:
        hook_state = spec.on_pre_send(db, signup, event) or {}
        db.commit()

    context = {**spec.build_context(event), **hook_state}
    # Hook-state's private keys (prefix _) are bookkeeping for
    # ``on_failure`` / ``on_success`` callbacks; not for the template.
    template_context = {k: v for k, v in context.items() if not k.startswith("_")}

    sent = send_with_retry(
        to=plaintext,
        template_name=spec.template_name,
        context=template_context,
        locale=event.locale,
        message_id=message_id,
        log_event=f"{spec.channel.value}_send_failed",
    )

    _finalise(
        db,
        spec,
        signup,
        dispatch,
        sent=sent,
        message_id=message_id if sent else None,
        hook_state=hook_state,
    )


def _finalise(
    db: Session,
    spec: "ChannelSpec",
    signup: Signup,
    dispatch: SignupEmailDispatch,
    *,
    sent: bool,
    message_id: str | None,
    hook_state: dict[str, Any],
) -> None:
    """Conditional status flip + per-channel cleanup hook +
    ciphertext wipe. The status UPDATE is filtered on
    ``status='pending'`` so a parallel worker / toggle-off
    cleanup that flipped the row out from under us isn't
    stomped."""
    new_status = EmailStatus.SENT if sent else EmailStatus.FAILED
    updated = (
        db.query(SignupEmailDispatch)
        .filter(
            SignupEmailDispatch.id == dispatch.id,
            SignupEmailDispatch.status == EmailStatus.PENDING,
        )
        .update(
            {
                SignupEmailDispatch.status: new_status,
                SignupEmailDispatch.sent_at: datetime.now(UTC),
                SignupEmailDispatch.message_id: message_id,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        # Status moved out from under us — drop any per-channel
        # bookkeeping we accumulated (e.g. feedback token).
        if spec.on_failure is not None:
            spec.on_failure(db, signup, hook_state)
        logger.info(
            "dispatch_skipped_status_changed",
            channel=spec.channel.value,
            signup_id=signup.id,
        )
        return

    if not sent and spec.on_failure is not None:
        spec.on_failure(db, signup, hook_state)
    elif sent and spec.on_success is not None:
        spec.on_success(db, signup, hook_state)

    _wipe_ciphertext_if_done(db, signup.id)

    logger.info(
        "dispatch_processed",
        channel=spec.channel.value,
        signup_id=signup.id,
        sent=sent,
    )
    emit_metric(channel=spec.channel.value, outcome="sent" if sent else "failed")


def run_once(spec: "ChannelSpec") -> int:
    """One sweep for one channel. Selects pending dispatches
    whose event currently satisfies the channel's window
    predicate, processes each, returns the count.

    Sized by ``EMAIL_BATCH_SIZE`` (default 200). Ordered by
    dispatch.id (uuid7) so the batch limit doesn't starve later
    rows across ticks — earliest-claimed first."""
    now = datetime.now(UTC)
    batch = email_batch_size()
    db = SessionLocal()
    try:
        rows = (
            db.query(SignupEmailDispatch, Signup, Event)
            .join(Signup, Signup.id == SignupEmailDispatch.signup_id)
            .join(Event, Event.entity_id == Signup.event_id)
            .filter(
                SignupEmailDispatch.channel == spec.channel,
                SignupEmailDispatch.status == EmailStatus.PENDING,
                Signup.encrypted_email.is_not(None),
                Event.valid_until.is_(None),
                spec.event_toggle.is_(True),
                spec.window_predicate(now),
            )
            .order_by(SignupEmailDispatch.id)
            .limit(batch)
            .all()
        )
        for dispatch, signup, event in rows:
            _process_one(db, spec, signup, event, dispatch)
        db.commit()
        return len(rows)
    finally:
        db.close()


def run_for_event(spec: "ChannelSpec", event_entity_id: str) -> int:
    """Manual trigger: process every still-pending dispatch on a
    single event for a given channel. Used by the organiser-side
    'send feedback now' button. Skips the window predicate."""
    db = SessionLocal()
    try:
        rows = (
            db.query(SignupEmailDispatch, Signup, Event)
            .join(Signup, Signup.id == SignupEmailDispatch.signup_id)
            .join(Event, Event.entity_id == Signup.event_id)
            .filter(
                Event.entity_id == event_entity_id,
                Event.valid_until.is_(None),
                SignupEmailDispatch.channel == spec.channel,
                SignupEmailDispatch.status == EmailStatus.PENDING,
                Signup.encrypted_email.is_not(None),
            )
            .order_by(SignupEmailDispatch.id)
            .limit(email_batch_size())
            .all()
        )
        for dispatch, signup, event in rows:
            _process_one(db, spec, signup, event, dispatch)
        db.commit()
        return len(rows)
    finally:
        db.close()
