"""Signup + dispatch-row construction for dispatcher / reaper tests.

A booking is a ``Registration`` (order header: name, party size, edit
link) with one ``Signup`` line item per occurrence. ``make_signup``
mirrors the public router: a booking on the event's first occurrence
(override with ``occurrence=``), with one ``EmailDispatch`` per applicable
channel keyed on that occurrence. Tests can override per-channel to seed
any (occurrence, channel, status) state directly.
"""

from sqlalchemy.orm import Session

from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailStatus,
    Event,
    Occurrence,
    Registration,
    Signup,
)
from backend.services import edit_token, encryption

from .events import first_occurrence


def _occurrence_id(signup_or_occurrence: object) -> str:
    """Resolve the various things tests pass to an occurrence id: a
    ``Signup`` line item, an ``Occurrence`` row, or a plain id string."""
    if isinstance(signup_or_occurrence, Signup):
        return signup_or_occurrence.occurrence_id
    if isinstance(signup_or_occurrence, Occurrence):
        return signup_or_occurrence.id
    return signup_or_occurrence  # type: ignore[return-value]


def make_signup(
    db: Session,
    event: Event,
    *,
    email: str | None = "alice@example.test",
    feedback: str | bool | None = None,
    reminder: str | bool | None = None,
    display_name: str = "Alice",
    party_size: int = 1,
    occurrence: Occurrence | None = None,
) -> Signup:
    """Insert a booking (registration + one line item) plus its dispatch
    rows on ``occurrence`` (defaults to the event's first occurrence).

    ``feedback`` / ``reminder`` accept:

    * ``None`` (default) — derive from ``email`` and the event's toggle,
      mirroring the signups router. ``"pending"`` if the channel applies,
      otherwise no dispatch row.
    * ``False`` — explicitly skip the dispatch row.
    * a status string (``"pending"``, ``"sent"``, ``"failed"``) — insert
      a dispatch row at that status.
    """
    occ = occurrence or first_occurrence(event)
    if feedback is None:
        feedback = "pending" if email and event.feedback_enabled else False
    if reminder is None:
        reminder = "pending" if email and event.reminder_enabled else False

    _, token_hash = edit_token.new_edit_token()
    registration = Registration(
        event_id=event.id,
        display_name=display_name,
        party_size=party_size,
        edit_token_hash=token_hash,
    )
    db.add(registration)
    db.flush()
    signup = Signup(
        registration_id=registration.id,
        occurrence_id=occ.id,
        source_choice="Mond-tot-mond",
        help_choices=[],
    )
    db.add(signup)
    db.flush()

    # Pending dispatches carry the encrypted address; terminal-state rows
    # have it nulled (matches the production lifecycle).
    def _ciphertext_for(status: EmailStatus) -> bytes | None:
        if email is None or status != EmailStatus.PENDING:
            return None
        return encryption.encrypt(email)

    if feedback:
        st = EmailStatus(feedback)
        db.add(
            EmailDispatch(
                occurrence_id=occ.id,
                channel=EmailChannel.FEEDBACK,
                status=st,
                encrypted_email=_ciphertext_for(st),
            )
        )
    if reminder:
        st = EmailStatus(reminder)
        db.add(
            EmailDispatch(
                occurrence_id=occ.id,
                channel=EmailChannel.REMINDER,
                status=st,
                encrypted_email=_ciphertext_for(st),
            )
        )
    db.flush()
    return signup


def get_dispatch(db: Session, signup_or_occurrence: object, channel: EmailChannel) -> EmailDispatch | None:
    """Fetch the (occurrence, channel) dispatch row. Accepts a ``Signup``
    line item (we read its ``occurrence_id``), an ``Occurrence``, or a
    plain occurrence-id string.

    Tests use one signup per occurrence, so (occurrence_id, channel)
    uniquely identifies the dispatch the helper just inserted — mirroring
    the production assumption that a public signup creates at most one
    dispatch per channel per occurrence."""
    occurrence_id = _occurrence_id(signup_or_occurrence)
    return (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.occurrence_id == occurrence_id,
            EmailDispatch.channel == channel,
        )
        .first()
    )


def has_any_ciphertext(db: Session, signup_or_occurrence: object) -> bool:
    """True if any dispatch row for this occurrence still carries an
    encrypted address. One signup per occurrence in tests, so "this
    signup's ciphertext is gone" is the same as "no dispatch on this
    occurrence carries ciphertext"."""
    occurrence_id = _occurrence_id(signup_or_occurrence)
    return (
        db.query(EmailDispatch)
        .filter(
            EmailDispatch.occurrence_id == occurrence_id,
            EmailDispatch.encrypted_email.is_not(None),
        )
        .first()
        is not None
    )
