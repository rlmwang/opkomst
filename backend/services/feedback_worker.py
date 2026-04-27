"""Post-event feedback sweep.

Runs hourly (wired from ``backend/main.py`` via APScheduler). For every
signup whose parent event ended ≥24h ago, that has an encrypted email
and hasn't been processed yet:

  1. Mint a one-time URL-safe token, store the token row.
  2. Generate a stable Message-ID for SMTP correlation.
  3. Decrypt the email.
  4. Render the localised body and hand it to SMTP with the
     Message-ID header (one retry on failure).
  5. **Always** null the encrypted blob and stamp ``feedback_sent_at``,
     whether the send succeeded or failed-after-retry. We do not keep
     ciphertext around "just in case" — see CLAUDE.md.
  6. Update ``feedback_email_status`` to "sent" or "failed".
  7. If sending failed, drop both the token (no point keeping it
     when it can never be redeemed) and the message id (no provider
     ever heard about it). The Scaleway TEM bounce webhook can later
     flip a "sent" status to "bounced".

This is the only legitimate caller of ``services.encryption.decrypt``.
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Event, FeedbackToken, Signup
from . import email_lifecycle, encryption, scd2
from .email import build_url, send_email_sync

logger = structlog.get_logger()

# How long the feedback link in the email stays valid. Long enough that
# someone who finds the email a couple of weeks later can still respond.
TOKEN_TTL = timedelta(days=30)


def _message_id_domain() -> str:
    return os.environ.get("MESSAGE_ID_DOMAIN", "opkomst.nu")


def _new_message_id() -> str:
    return f"<{secrets.token_hex(16)}@{_message_id_domain()}>"


def _mint_token(db: Session, signup: Signup, event: Event) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        FeedbackToken(
            token=token,
            signup_id=signup.id,
            # Stable logical id, so the token survives event edits.
            event_id=event.entity_id,
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
    message_id: str | None = None
    if plaintext is not None:
        token = _mint_token(db, signup, event)
        message_id = _new_message_id()
        feedback_url = build_url(f"e/{event.slug}/feedback", t=token)
        for attempt in range(2):
            try:
                send_email_sync(
                    to=plaintext,
                    template_name="feedback.html",
                    context={"event_name": event.name, "feedback_url": feedback_url},
                    locale=event.locale,
                    message_id=message_id,
                )
                sent = True
                break
            except Exception:
                logger.exception("feedback_send_failed", signup_id=signup.id, attempt=attempt)

    signup.feedback_sent_at = datetime.now(UTC)
    if sent:
        signup.feedback_email_status = "sent"
        signup.feedback_message_id = message_id
    else:
        signup.feedback_email_status = "failed"
        if token:
            db.query(FeedbackToken).filter(FeedbackToken.token == token).delete()
        signup.feedback_message_id = None
    # Wipe the ciphertext only when no other pending email activity
    # remains (e.g. a reminder that hasn't fired yet); see
    # ``email_lifecycle`` for the rule.
    email_lifecycle.wipe_if_done(signup)
    db.add(signup)

    logger.info("feedback_processed", signup_id=signup.id, sent=sent)


def run_once() -> int:
    """One sweep. Returns the number of signups processed."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    db = SessionLocal()
    try:
        # Join via entity_id (the stable logical id) and only the
        # current Event version. Past versions are history; we never
        # send feedback emails on behalf of an old revision.
        rows = (
            db.query(Signup, Event)
            .join(Event, Signup.event_id == Event.entity_id)
            .filter(
                Event.valid_until.is_(None),
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


def run_for_event(entity_id: str) -> int:
    """Process every still-pending signup on a single event, ignoring
    the 24h cutoff. Used by the organiser-triggered "send now" button.
    ``entity_id`` is the stable logical id (``EventOut.id``).
    Returns the number processed."""
    db = SessionLocal()
    try:
        event = scd2.current_by_entity(db, Event, entity_id)
        if not event:
            return 0
        rows = (
            db.query(Signup)
            .filter(
                Signup.event_id == entity_id,
                Signup.encrypted_email.is_not(None),
                Signup.feedback_sent_at.is_(None),
            )
            .all()
        )
        for signup in rows:
            _process_one(db, signup, event)
        db.commit()
        return len(rows)
    finally:
        db.close()
