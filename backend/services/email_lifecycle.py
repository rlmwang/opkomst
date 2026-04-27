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

from ..models import Signup


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
