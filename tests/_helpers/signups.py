"""Signup + dispatch-row construction for dispatcher / reaper tests.

Mirrors the public signups router's logic by default: a Signup with
an email gets one ``EmailDispatch`` row per applicable channel
(controlled by the event's toggles). Tests can override per-channel
to seed any (signup, channel, status) state directly.
"""

from sqlalchemy.orm import Session

from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    Signup,
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
    * a status string (``"pending"``, ``"sent"``, ``"failed"``)
      — insert a dispatch row at that status.
    """
    if feedback is None:
        feedback = "pending" if email and event.feedback_enabled else False
    if reminder is None:
        reminder = "pending" if email and event.reminder_enabled else False

    signup = Signup(
        event_id=event.id,
        display_name=display_name,
        party_size=1,
        source_choice="Mond-tot-mond",
        help_choices=[],
    )
    db.add(signup)
    db.flush()

    # Pending dispatches carry the encrypted address; terminal-
    # state rows have it nulled (matches the production lifecycle).
    def _ciphertext_for(status: EmailStatus) -> bytes | None:
        if email is None or status != EmailStatus.PENDING:
            return None
        return encryption.encrypt(email)

    if feedback:
        st = EmailStatus(feedback)
        db.add(
            EmailDispatch(
                event_id=event.id,
                channel=EmailChannel.FEEDBACK,
                status=st,
                encrypted_email=_ciphertext_for(st),
            )
        )
    if reminder:
        st = EmailStatus(reminder)
        db.add(
            EmailDispatch(
                event_id=event.id,
                channel=EmailChannel.REMINDER,
                status=st,
                encrypted_email=_ciphertext_for(st),
            )
        )
    db.flush()
    return signup


def get_dispatch(db: Session, signup_or_event_id: object, channel: EmailChannel) -> EmailDispatch | None:
    """Fetch the (event, channel) dispatch row. Accepts either a
    ``Signup`` instance (we read its ``event_id``) or a plain
    ``event_id`` string. Most tests pass the Signup their setup
    helper just inserted; a few pass the event id directly when
    they don't have a Signup handy.

    Tests use one signup per event, so (event_id, channel)
    uniquely identifies the dispatch the helper just inserted —
    mirroring the production assumption that a public signup
    creates at most one dispatch per channel."""
    event_id = signup_or_event_id.event_id if isinstance(signup_or_event_id, Signup) else signup_or_event_id
    return (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.event_id == event_id,
            EmailDispatch.channel == channel,
        )
        .first()
    )


def has_any_ciphertext(db: Session, signup_or_event_id: object) -> bool:
    """True if any dispatch row for this event still carries an
    encrypted address. Mirrors the test contract for ``get_dispatch``
    above — one signup per event in tests, so "this signup's
    ciphertext is gone" is the same as "no dispatch on this event
    carries ciphertext"."""
    event_id = signup_or_event_id.event_id if isinstance(signup_or_event_id, Signup) else signup_or_event_id
    return (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.event_id == event_id,
            EmailDispatch.encrypted_email.is_not(None),
        )
        .first()
        is not None
    )
