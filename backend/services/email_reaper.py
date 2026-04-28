"""Four classes of cleanup that all amount to "scan dispatches,
remove or finalise rows, wipe ciphertext if nothing else
pending":

* ``reap_partial_sends`` — boot-time + hourly. Catches rows
  that crashed mid-send (status='pending' but message_id set).
  Flips them to 'failed' and stamps sent_at, so the regular
  sweep won't re-process them. Privacy invariant kicks in: any
  signup with no remaining pending dispatch loses its
  ciphertext.

* ``reap_expired_windows`` — daily. Finds reminder dispatches
  whose event has already started (the 72h pre-event window
  passed during a worker outage). Deletes the dispatch — there's
  nothing useful to send, no audit need to record "we didn't".

* ``retire_event_channels`` — called from the events router when
  an organiser disables a toggle. Deletes pending dispatches for
  the affected (event, channel) pairs. ``message_id IS NULL``
  filter excludes rows currently mid-send by a worker, so a
  toggle-off can never stomp an in-flight send.

* ``purge_post_event_emails`` — daily privacy backstop. ≥7 days
  after an event ends, every legitimate wipe path (successful
  send, toggle-off cleanup, partial-send reaper, expired-window
  reaper) should already have nulled the ciphertext. If anything
  is still present, this sweep wipes it unconditionally and logs
  a warning so the underlying bug surfaces. Under normal
  operation this is a no-op.

All four end with a ciphertext-wipe pass so the privacy
invariant ("encrypted_email is NULL when no pending dispatch
remains") is upheld atomically.
"""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import EmailChannel, EmailStatus, Event, Signup, SignupEmailDispatch

logger = structlog.get_logger()

# How long after an event ends before we force-wipe any remaining
# ciphertext for its signups. Comfortably past every other path:
# the reminder window closes at event start, feedback fires 24h
# after end, retries finish within hours, and the daily reapers
# clean up anything stuck. A week is "the system has had every
# chance".
POST_EVENT_PURGE_DELAY = timedelta(days=7)


def _wipe_orphaned_ciphertext(db: Session) -> None:
    """For every signup that no longer has a pending dispatch,
    NULL ``encrypted_email``. Run after every reaper to keep the
    privacy invariant tight."""
    pending_exists = (
        db.query(SignupEmailDispatch.id)
        .filter(
            SignupEmailDispatch.signup_id == Signup.id,
            SignupEmailDispatch.status == EmailStatus.PENDING,
        )
        .exists()
    )
    db.query(Signup).filter(
        Signup.encrypted_email.is_not(None),
        ~pending_exists,
    ).update({Signup.encrypted_email: None}, synchronize_session=False)


# ---- 1. Partial-send recovery ------------------------------------


def reap_partial_sends(db: Session) -> int:
    """Sweep dispatches stuck at ``pending`` with a message_id.
    Those crashed mid-send. Flip to ``failed`` so the regular
    worker query no longer returns them; wipe the orphaned
    ciphertext."""
    now = datetime.now(UTC)
    reaped = (
        db.query(SignupEmailDispatch)
        .filter(
            SignupEmailDispatch.status == EmailStatus.PENDING,
            SignupEmailDispatch.message_id.is_not(None),
        )
        .update(
            {
                SignupEmailDispatch.status: EmailStatus.FAILED,
                SignupEmailDispatch.sent_at: now,
            },
            synchronize_session=False,
        )
    )
    _wipe_orphaned_ciphertext(db)
    db.commit()
    if reaped:
        logger.warning("reaped_partial_sends", count=reaped)
    return reaped


# ---- 2. Expired-window cleanup -----------------------------------


def reap_expired_windows() -> int:
    """Catch up on reminder dispatches whose event already
    started during a multi-day worker outage. The regular sweep
    would never pick them up (its filter excludes events whose
    starts_at is in the past), so they'd sit ``pending`` forever
    and the ciphertext would never wipe.

    Deletes the dispatch row entirely — the channel no longer
    applies, and we don't need an audit record of 'we didn't
    send this email because we were down'."""
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        # Correlated subquery: which events have already
        # started? Works on both SQLite and Postgres without
        # dragging every entity_id through Python.
        expired_event_exists = (
            db.query(Event.entity_id)
            .filter(
                Event.valid_until.is_(None),
                Event.starts_at <= now,
                Event.entity_id == Signup.event_id,
            )
            .exists()
        )
        signup_in_expired_event = (
            db.query(Signup.id)
            .filter(
                Signup.id == SignupEmailDispatch.signup_id,
                expired_event_exists,
            )
            .exists()
        )

        reaped = (
            db.query(SignupEmailDispatch)
            .filter(
                SignupEmailDispatch.channel == EmailChannel.REMINDER,
                SignupEmailDispatch.status == EmailStatus.PENDING,
                signup_in_expired_event,
            )
            .delete(synchronize_session=False)
        )
        _wipe_orphaned_ciphertext(db)
        db.commit()
        if reaped:
            logger.info("reaped_expired_windows", count=reaped)
        return reaped
    finally:
        db.close()


# ---- 3. Toggle-off cleanup ---------------------------------------


def retire_event_channels(
    db: Session,
    *,
    event_entity_id: str,
    channels: set[EmailChannel],
) -> None:
    """An organiser flipped one or more channels off on this
    event. Delete pending dispatches for the affected channels;
    leave any in-flight sends (``message_id IS NOT NULL``)
    alone — those will finalise on their own.

    Wipes ciphertext for any signup that no longer has a pending
    dispatch."""
    if not channels:
        return
    db.query(SignupEmailDispatch).filter(
        SignupEmailDispatch.channel.in_(channels),
        SignupEmailDispatch.status == EmailStatus.PENDING,
        SignupEmailDispatch.message_id.is_(None),
        SignupEmailDispatch.signup_id.in_(
            db.query(Signup.id).filter(Signup.event_id == event_entity_id)
        ),
    ).delete(synchronize_session=False)
    _wipe_orphaned_ciphertext(db)


# ---- 4. Post-event privacy backstop ------------------------------


def purge_post_event_emails() -> int:
    """≥7 days after an event ends, force-wipe any remaining
    ciphertext for its signups. Every other wipe path should
    already have run by this point — if this sweep finds
    anything, that's a bug and we surface it via a warning log
    so it can be investigated. Under normal operation this is a
    no-op."""
    now = datetime.now(UTC)
    cutoff = now - POST_EVENT_PURGE_DELAY
    db = SessionLocal()
    try:
        # Subquery: signup IDs whose current event ended ≥7 days
        # ago. Correlated against Signup so it works on both
        # SQLite and Postgres without dragging entity_ids through
        # Python.
        old_event_signup = (
            db.query(Event.entity_id)
            .filter(
                Event.valid_until.is_(None),
                Event.ends_at <= cutoff,
                Event.entity_id == Signup.event_id,
            )
            .exists()
        )
        wiped = (
            db.query(Signup)
            .filter(
                Signup.encrypted_email.is_not(None),
                old_event_signup,
            )
            .update(
                {Signup.encrypted_email: None},
                synchronize_session=False,
            )
        )
        db.commit()
        if wiped:
            # Warning, not info: under normal operation every
            # legitimate path should already have wiped these.
            logger.warning("post_event_email_purge", count=wiped)
        return wiped
    finally:
        db.close()
