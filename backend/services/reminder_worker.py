"""Pre-event reminder sweep.

Runs hourly (wired from ``backend/worker.py`` via APScheduler).
For every signup whose parent event has ``reminder_enabled`` and
starts within the next 72 hours, that has an encrypted email and
a ``reminder_email_status`` still ``"pending"``:

  1. Pre-mint a Message-ID and persist it on the row before
     touching SMTP (Phase 2.1: a process kill between commit and
     SMTP-ack leaves the row recoverable by the boot-time
     ``email_lifecycle.reap_partial_sends``).
  2. Decrypt the email. A failure is unrecoverable — flip status
     to ``failed`` immediately and never re-process this row
     (Phase 2.2).
  3. Render the localised reminder body and hand it to SMTP with
     the Message-ID header (one retry on failure).
  4. Stamp ``reminder_sent_at`` and flip status to ``sent`` or
     ``failed`` via a conditional UPDATE filtered on
     ``status == 'pending'`` so a parallel worker / toggle-off
     cleanup can't be stomped (Phase 1.2).
  5. Wipe the ciphertext when no channel is still ``pending``,
     using a DB-side conditional UPDATE so a concurrent
     feedback-worker commit is visible.

A second legitimate caller of ``services.encryption.decrypt``
(the other being ``services.feedback_worker``).
"""

from datetime import UTC, datetime, timedelta

import structlog

from ..database import SessionLocal
from ..models import Event, Signup
from . import encryption
from .email import build_url, email_batch_size, emit_metric, new_message_id, send_with_retry

logger = structlog.get_logger()

# Reminders fire when the event is within this window of starting.
# Anything further out waits for the next sweep; anything closer
# (e.g. an event happening tomorrow) just fires on the next tick.
REMINDER_WINDOW = timedelta(hours=72)


def _process_one(db, signup: Signup, event: Event) -> None:
    # Step 1 — Atomically claim the row by setting message_id
    # only when it's still NULL and the status is still pending.
    # See ``feedback_worker._process_one`` for the rationale; this
    # is the claim mechanism that prevents two parallel workers
    # from both SMTP-ack-ing the same signup.
    message_id = new_message_id()
    claimed = (
        db.query(Signup)
        .filter(
            Signup.id == signup.id,
            Signup.reminder_email_status == "pending",
            Signup.reminder_message_id.is_(None),
        )
        .update(
            {Signup.reminder_message_id: message_id},
            synchronize_session=False,
        )
    )
    db.commit()
    if claimed == 0:
        logger.info("reminder_skipped_already_claimed", signup_id=signup.id)
        return

    # Step 2 — Decrypt. Decrypt failures aren't recoverable; flip
    # to ``failed`` immediately and never come back to this row.
    try:
        plaintext = encryption.decrypt(signup.encrypted_email or b"")
    except Exception:
        logger.exception("reminder_decrypt_failed", signup_id=signup.id)
        _finalise(db, signup, sent=False, message_id=None)
        return

    # Step 3 — Send.
    event_url = build_url(f"e/{event.slug}")
    sent = send_with_retry(
        to=plaintext,
        template_name="reminder.html",
        context={
            "event_name": event.name,
            "event_url": event_url,
            "starts_at": event.starts_at,
        },
        locale=event.locale,
        message_id=message_id,
        log_event="reminder_send_failed",
    )

    _finalise(db, signup, sent=sent, message_id=message_id if sent else None)


def _finalise(
    db,
    signup: Signup,
    *,
    sent: bool,
    message_id: str | None,
) -> None:
    """Conditional status flip + DB-side ciphertext wipe."""
    new_status = "sent" if sent else "failed"
    updated = (
        db.query(Signup)
        .filter(
            Signup.id == signup.id,
            Signup.reminder_email_status == "pending",
        )
        .update(
            {
                Signup.reminder_sent_at: datetime.now(UTC),
                Signup.reminder_email_status: new_status,
                Signup.reminder_message_id: message_id,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        logger.info("reminder_skipped_status_changed", signup_id=signup.id)
        return

    # Wipe the ciphertext only when no channel still has pending
    # activity. DB-side conditional sees concurrent commits.
    db.query(Signup).filter(
        Signup.id == signup.id,
        Signup.feedback_email_status != "pending",
        Signup.reminder_email_status != "pending",
    ).update({Signup.encrypted_email: None}, synchronize_session=False)

    logger.info("reminder_processed", signup_id=signup.id, sent=sent)
    emit_metric(channel="reminder", outcome="sent" if sent else "failed")


def reap_expired() -> int:
    """Sweep rows whose reminder is still ``pending`` for an event
    that has already started — the 72-hour window has passed and
    no reminder will ever be useful. Flip them to
    ``not_applicable`` and wipe the ciphertext if no other channel
    is still pending. Without this, a multi-day worker outage
    would leave rows ``pending`` forever, since the regular
    sweep's filter excludes events whose ``starts_at`` is in the
    past. Wired as a daily job in ``backend/worker.py``.
    Returns the number of rows reaped."""
    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        # Correlated subquery — works on both SQLite and Postgres,
        # and unlike the previous "load entity_ids into a Python
        # list and IN-clause" approach has no upper bound on the
        # row count: a long-lived DB with thousands of past events
        # would otherwise drag every entity_id through the worker
        # process every 24h.
        expired_event_exists = (
            db.query(Event.entity_id)
            .filter(
                Event.valid_until.is_(None),
                Event.starts_at <= now,
                Event.entity_id == Signup.event_id,
            )
            .exists()
        )

        reaped = (
            db.query(Signup)
            .filter(
                Signup.reminder_email_status == "pending",
                expired_event_exists,
            )
            .update(
                {
                    Signup.reminder_email_status: "not_applicable",
                    # Stamp ``sent_at`` so reaped rows match the
                    # same "settled ⇒ sent_at != NULL" invariant
                    # the regular ``_finalise`` path maintains.
                    Signup.reminder_sent_at: now,
                },
                synchronize_session=False,
            )
        )
        # Wipe ciphertext on rows of expired events whose channels
        # are now both settled — same DB-side rule the per-row
        # workers use.
        db.query(Signup).filter(
            expired_event_exists,
            Signup.feedback_email_status != "pending",
            Signup.reminder_email_status != "pending",
        ).update({Signup.encrypted_email: None}, synchronize_session=False)
        db.commit()
        if reaped:
            logger.info("reminder_reap_expired", count=reaped)
        return reaped
    finally:
        db.close()


def run_once() -> int:
    """One sweep. Returns the number of signups processed."""
    now = datetime.now(UTC)
    deadline = now + REMINDER_WINDOW
    batch_size = email_batch_size()
    db = SessionLocal()
    try:
        # Gate on the event toggle being currently true *and* the
        # event being inside the 72h window. Past events are
        # excluded because there's nothing to remind anyone of.
        rows = (
            db.query(Signup, Event)
            .join(Event, Signup.event_id == Event.entity_id)
            .filter(
                Event.valid_until.is_(None),
                Event.reminder_enabled.is_(True),
                Event.starts_at > now,
                Event.starts_at <= deadline,
                Signup.encrypted_email.is_not(None),
                Signup.reminder_email_status == "pending",
            )
            # FIFO ordering by signup id (uuid7 is time-sortable)
            # so the batch limit doesn't starve later signups
            # across ticks.
            .order_by(Signup.id)
            .limit(batch_size)
            .all()
        )
        for signup, event in rows:
            _process_one(db, signup, event)
        db.commit()
        return len(rows)
    finally:
        db.close()
