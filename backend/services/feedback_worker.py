"""Post-event feedback sweep.

Runs hourly (wired from ``backend/main.py`` via APScheduler). For every
signup whose parent event ended ≥24h ago, that has an encrypted email
and hasn't been processed yet:

  1. Decrypt the email.
  2. Send the feedback form (one retry on failure).
  3. **Always** null the encrypted blob and stamp ``feedback_sent_at``,
     whether the send succeeded or failed-after-retry. We do not keep
     ciphertext around "just in case" — see CLAUDE.md.

This is the only legitimate caller of ``services.encryption.decrypt``.
"""

import os
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Event, Signup
from . import encryption
from .email import send_email

logger = structlog.get_logger()

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def _build_body(event: Event) -> str:
    feedback_url = f"{PUBLIC_BASE_URL}/e/{event.slug}/feedback"
    return (
        f"Bedankt voor je komst naar {event.name}.\n\n"
        f"Wil je ons in twee minuten laten weten hoe het was? {feedback_url}\n\n"
        "Dit is de enige mail die je van ons krijgt; je adres is na verzending verwijderd."
    )


def _process_one(db: Session, signup: Signup, event: Event) -> None:
    # Default to "processed" so we always clear the ciphertext, even on failure.
    plaintext: str | None = None
    try:
        plaintext = encryption.decrypt(signup.encrypted_email or b"")
    except Exception:
        logger.exception("feedback_decrypt_failed", signup_id=signup.id)

    sent = False
    if plaintext is not None:
        for attempt in range(2):
            try:
                send_email(
                    to=plaintext,
                    subject=f"Feedback: {event.name}",
                    body=_build_body(event),
                )
                sent = True
                break
            except Exception:
                logger.exception("feedback_send_failed", signup_id=signup.id, attempt=attempt)

    # Always wipe the ciphertext — privacy invariant.
    signup.encrypted_email = None
    signup.feedback_sent_at = datetime.now(UTC)
    db.add(signup)
    logger.info("feedback_processed", signup_id=signup.id, sent=sent)


def run_once() -> int:
    """One sweep. Returns the number of signups processed."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    db = SessionLocal()
    try:
        rows = (
            db.query(Signup, Event)
            .join(Event, Signup.event_id == Event.id)
            .filter(
                Signup.encrypted_email.is_not(None),
                Signup.feedback_sent_at.is_(None),
                Event.ends_at <= cutoff,
            )
            .all()
        )
        for signup, event in rows:
            _process_one(db, signup, event)
        db.commit()
        return len(rows)
    finally:
        db.close()
