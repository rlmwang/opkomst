"""Shared rules for the encrypted-email lifecycle on a Signup.

A signup carries an encrypted email iff at least one of the
event's email features is enabled when the signup happens. While
the email is in our possession we may use it for two distinct
sends — a reminder (~3 days before the event) and a feedback link
(~24 hours after) — gated independently by the event's
``reminder_enabled`` and ``questionnaire_enabled`` toggles.

Privacy invariant: the ciphertext is wiped the moment every
*pending* email activity for that signup is settled. So:

* reminder-only event: wipe right after the reminder send is
  resolved (sent or failed-after-retry).
* feedback-only event: wipe after the feedback send is resolved
  (existing behaviour).
* both toggles on: wipe after the feedback send (which always
  comes after the reminder in the timeline).
* organiser flips a toggle off mid-flight: that channel is
  retired to ``not_applicable`` immediately and, if the other
  channel was already done, the ciphertext is wiped on the spot.

Centralising the rule here keeps the worker code free of
"do we have any other pending email?" book-keeping at every
call site.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from ..models import Signup

logger = structlog.get_logger()


def has_pending_email_activity(signup: Signup) -> bool:
    """True iff at least one channel is still waiting to fire."""
    return (
        signup.feedback_email_status == "pending"
        or signup.reminder_email_status == "pending"
    )


def wipe_if_done(signup: Signup) -> None:
    """Null the ciphertext when no pending channel remains."""
    if not has_pending_email_activity(signup):
        signup.encrypted_email = None


def reap_partial_sends(db: Session) -> int:
    """Sweep rows whose status is ``pending`` but whose
    message_id is set — those are stuck mid-send from a process
    that crashed between persisting the message_id and getting
    the SMTP ack (or, more commonly, between SMTP ack and the
    subsequent status flip). Flip them to ``failed``: the
    recipient may have got the email already (so retrying would
    duplicate) but we have no way to find out.

    Called on worker boot, before the first sweep. Returns the
    total number of rows reaped across both channels."""
    now = datetime.now(UTC)
    # Stamp ``*_sent_at`` along with the status flip so the row
    # honours the same "settled rows have a sent_at timestamp"
    # invariant ``_finalise`` maintains. Without it, the regular
    # sweep query (which can fall back to ``sent_at IS NULL``)
    # would still re-fetch reaped rows.
    feedback_count = (
        db.query(Signup)
        .filter(
            Signup.feedback_email_status == "pending",
            Signup.feedback_message_id.is_not(None),
        )
        .update(
            {
                Signup.feedback_email_status: "failed",
                Signup.feedback_sent_at: now,
            },
            synchronize_session=False,
        )
    )
    reminder_count = (
        db.query(Signup)
        .filter(
            Signup.reminder_email_status == "pending",
            Signup.reminder_message_id.is_not(None),
        )
        .update(
            {
                Signup.reminder_email_status: "failed",
                Signup.reminder_sent_at: now,
            },
            synchronize_session=False,
        )
    )
    # Wipe ciphertext on rows where neither channel is pending now —
    # could be ones we just reaped, or ones whose other channel
    # was already settled.
    db.query(Signup).filter(
        Signup.feedback_email_status != "pending",
        Signup.reminder_email_status != "pending",
    ).update({Signup.encrypted_email: None}, synchronize_session=False)
    db.commit()

    if feedback_count or reminder_count:
        logger.warning(
            "reaped_partial_sends",
            feedback=feedback_count,
            reminder=reminder_count,
        )
    return feedback_count + reminder_count
