"""Signup + dispatch-row construction for dispatcher / reaper tests.

Mirrors the public signups router's logic by default: a Signup with
an email gets one ``SignupEmailDispatch`` row per applicable channel
(controlled by the event's toggles). Tests can override per-channel
to seed any (signup, channel, status) state directly.
"""

from sqlalchemy.orm import Session

from backend.models import (
    EmailChannel,
    EmailStatus,
    Event,
    Signup,
    SignupEmailDispatch,
)
from backend.services import encryption


def make_signup(
    db: Session,
    event: Event,
    *,
    email: str | None = "alice@example.test",
    feedback: str | bool | None = None,
    reminder: str | bool | None = None,
    display_name: str = "Alice",
) -> Signup:
    """Insert a Signup row plus its dispatch rows.

    ``feedback`` / ``reminder`` accept:

    * ``None`` (default) — derive from ``email`` and the event's
      toggle, mirroring the signups router. ``"pending"`` if the
      channel applies, otherwise no dispatch row.
    * ``False`` — explicitly skip the dispatch row.
    * a status string (``"pending"``, ``"sent"``, ``"failed"``,
      ``"bounced"``, ``"complaint"``) — insert a dispatch row at
      that status.
    """
    if feedback is None:
        feedback = "pending" if email and event.questionnaire_enabled else False
    if reminder is None:
        reminder = "pending" if email and event.reminder_enabled else False

    signup = Signup(
        event_id=event.entity_id,
        display_name=display_name,
        party_size=1,
        source_choice="Mond-tot-mond",
        help_choices=[],
        encrypted_email=encryption.encrypt(email) if email else None,
    )
    db.add(signup)
    db.flush()

    if feedback:
        db.add(
            SignupEmailDispatch(
                signup_id=signup.id,
                channel=EmailChannel.FEEDBACK,
                status=EmailStatus(feedback),
            )
        )
    if reminder:
        db.add(
            SignupEmailDispatch(
                signup_id=signup.id,
                channel=EmailChannel.REMINDER,
                status=EmailStatus(reminder),
            )
        )
    db.flush()
    return signup


def get_dispatch(
    db: Session, signup_id: str, channel: EmailChannel
) -> SignupEmailDispatch | None:
    """Fetch the (signup, channel) dispatch row for assertions
    or in-test mutation (e.g. setting ``message_id`` to simulate
    a partial-send crash)."""
    return (
        db.query(SignupEmailDispatch)
        .filter(
            SignupEmailDispatch.signup_id == signup_id,
            SignupEmailDispatch.channel == channel,
        )
        .first()
    )
