"""Pre-event reminder sweep.

Runs hourly (wired from ``backend/main.py`` via APScheduler). For
every signup whose parent event has ``reminder_enabled`` and
starts within the next 72 hours, that has an encrypted email and
a ``reminder_email_status`` still ``"pending"``:

  1. Generate a stable Message-ID for SMTP correlation.
  2. Decrypt the email.
  3. Render the localised reminder body and hand it to SMTP with
     the Message-ID header (one retry on failure).
  4. Stamp ``reminder_sent_at`` and flip
     ``reminder_email_status`` to "sent" or "failed".
  5. Wipe the ciphertext via ``email_lifecycle.wipe_if_done`` —
     for events with the questionnaire toggle off, that's now;
     for events with the questionnaire still pending, wipe waits
     until the feedback worker also finishes.

A second legitimate caller of ``services.encryption.decrypt``
(the other being ``services.feedback_worker``).
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import structlog

from ..database import SessionLocal
from ..models import Event, Signup
from . import encryption
from .email import build_url, send_email_sync

logger = structlog.get_logger()

# Reminders fire when the event is within this window of starting.
# Anything further out waits for the next sweep; anything closer
# (e.g. an event happening tomorrow) just fires on the next tick.
REMINDER_WINDOW = timedelta(hours=72)


def _message_id_domain() -> str:
    return os.environ.get("MESSAGE_ID_DOMAIN", "opkomst.nu")


def _new_message_id() -> str:
    return f"<{secrets.token_hex(16)}@{_message_id_domain()}>"


def _process_one(db, signup: Signup, event: Event) -> None:
    plaintext: str | None = None
    try:
        plaintext = encryption.decrypt(signup.encrypted_email or b"")
    except Exception:
        logger.exception("reminder_decrypt_failed", signup_id=signup.id)

    sent = False
    message_id: str | None = None
    if plaintext is not None:
        message_id = _new_message_id()
        event_url = build_url(f"e/{event.slug}")
        for attempt in range(2):
            try:
                send_email_sync(
                    to=plaintext,
                    template_name="reminder.html",
                    context={
                        "event_name": event.name,
                        "event_url": event_url,
                        "starts_at": event.starts_at,
                    },
                    locale=event.locale,
                    message_id=message_id,
                )
                sent = True
                break
            except Exception:
                logger.exception("reminder_send_failed", signup_id=signup.id, attempt=attempt)

    # Conditional UPDATE — same defence-in-depth pattern as the
    # feedback worker. If the row's status moved under us, bail
    # without overwriting whatever the other process / toggle-off
    # cleanup decided.
    new_status = "sent" if sent else "failed"
    new_msg_id = message_id if sent else None
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
                Signup.reminder_message_id: new_msg_id,
            },
            synchronize_session=False,
        )
    )
    if updated == 0:
        logger.info("reminder_skipped_status_changed", signup_id=signup.id)
        return

    # Wipe the ciphertext only when no channel still has pending
    # activity. Conditional UPDATE re-reads from the DB, so a
    # concurrent feedback-worker commit is visible without
    # depending on the (stale) in-memory ORM state on ``signup``.
    db.query(Signup).filter(
        Signup.id == signup.id,
        Signup.feedback_email_status != "pending",
        Signup.reminder_email_status != "pending",
    ).update({Signup.encrypted_email: None}, synchronize_session=False)

    logger.info("reminder_processed", signup_id=signup.id, sent=sent)


def run_once() -> int:
    """One sweep. Returns the number of signups processed."""
    now = datetime.now(UTC)
    deadline = now + REMINDER_WINDOW
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
            .all()
        )
        for signup, event in rows:
            _process_one(db, signup, event)
        db.commit()
        return len(rows)
    finally:
        db.close()
