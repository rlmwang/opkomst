"""Post-event feedback sweep.

Runs hourly (wired from ``backend/main.py`` via APScheduler). For every
signup whose parent event ended ≥24h ago, that has an encrypted email
and hasn't been processed yet:

  1. Mint a one-time URL-safe token, store the token row.
  2. Decrypt the email.
  3. Render the localised subject + body (services.email_templates).
  4. Send the feedback form (one retry on failure).
  5. **Always** null the encrypted blob and stamp ``feedback_sent_at``,
     whether the send succeeded or failed-after-retry. We do not keep
     ciphertext around "just in case" — see CLAUDE.md.
  6. If sending failed, also delete the token (no point keeping it
     around when it can never be redeemed).

This is the only legitimate caller of ``services.encryption.decrypt``.
"""

import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Event, FeedbackToken, Signup
from . import encryption
from .email import build_url, send_email_sync

logger = structlog.get_logger()

# How long the feedback link in the email stays valid. Long enough that
# someone who finds the email a couple of weeks later can still respond.
TOKEN_TTL = timedelta(days=30)


def _mint_token(db: Session, signup: Signup, event: Event) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        FeedbackToken(
            token=token,
            signup_id=signup.id,
            event_id=event.id,
            expires_at=datetime.now(UTC) + TOKEN_TTL,
        )
    )
    db.flush()
    return token


def _process_one(db: Session, signup: Signup, event: Event) -> None:
    plaintext: str | None = None
    try:
        plaintext = encryption.decrypt(signup.encrypted_email or b"")
    except Exception:
        logger.exception("feedback_decrypt_failed", signup_id=signup.id)

    sent = False
    token: str | None = None
    if plaintext is not None:
        token = _mint_token(db, signup, event)
        feedback_url = build_url(f"e/{event.slug}/feedback", t=token)
        for attempt in range(2):
            try:
                send_email_sync(
                    to=plaintext,
                    template_name="feedback.html",
                    context={"event_name": event.name, "feedback_url": feedback_url},
                    locale="nl",
                )
                sent = True
                break
            except Exception:
                logger.exception("feedback_send_failed", signup_id=signup.id, attempt=attempt)

    # Always wipe the ciphertext — privacy invariant.
    signup.encrypted_email = None
    signup.feedback_sent_at = datetime.now(UTC)
    db.add(signup)

    # If the send ultimately failed, the token can never be redeemed
    # (the recipient never got the link). Drop it so the table doesn't
    # accumulate orphans.
    if not sent and token:
        db.query(FeedbackToken).filter(FeedbackToken.token == token).delete()

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
                Event.questionnaire_enabled.is_(True),
            )
            .all()
        )
        for signup, event in rows:
            _process_one(db, signup, event)
        db.commit()
        return len(rows)
    finally:
        db.close()
