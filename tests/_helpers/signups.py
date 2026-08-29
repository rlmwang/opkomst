"""Signup + dispatch-row construction for dispatcher / reaper tests.

A booking is a ``Registration`` (order header: name, party size, edit
link) with one ``Signup`` line item per occurrence. ``make_signup``
mirrors the public router: a booking on the event's first occurrence
(override with ``occurrence=``), with one ``EmailDispatch`` per applicable
channel keyed on that occurrence. Tests can override per-channel to seed
any (occurrence, channel) state directly.
"""

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models import (
    EmailChannel,
    EmailDispatch,
    EmailSendCount,
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
      mirroring the signups router: a pending row if the channel
      applies, otherwise nothing.
    * ``False`` — explicitly skip the dispatch row.
    * ``"pending"`` / ``True`` — insert the dispatch row.
    * ``"sent"`` / ``"failed"`` — the send already happened, so there is
      no row: record it in ``EmailSendCount`` instead, which is what the
      production lifecycle leaves behind.
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
    )
    db.add(signup)
    db.flush()

    def _place(channel: EmailChannel, state: str | bool) -> None:
        """A pending state is a row carrying the address; a finished one
        is a number and no row at all."""
        if state in (True, "pending"):
            db.add(
                EmailDispatch(
                    occurrence_id=occ.id,
                    channel=channel,
                    encrypted_email=encryption.encrypt(email) if email else None,
                )
            )
            return
        db.add(
            EmailSendCount(
                occurrence_id=occ.id,
                channel=channel,
                day=datetime.now(UTC).date(),
                sent=1 if state == "sent" else 0,
                failed=1 if state == "failed" else 0,
            )
        )

    if feedback:
        _place(EmailChannel.FEEDBACK, feedback)
    if reminder:
        _place(EmailChannel.REMINDER, reminder)
    db.flush()
    return signup


def send_counts(db: Session, signup_or_occurrence: object, channel: EmailChannel) -> tuple[int, int]:
    """``(sent, failed)`` recorded for an (occurrence, channel), summed
    across days. A finished send leaves no dispatch row, so this is what
    the assertions that used to read ``status`` ask instead."""
    occurrence_id = _occurrence_id(signup_or_occurrence)
    row = (
        db.query(
            func.coalesce(func.sum(EmailSendCount.sent), 0),
            func.coalesce(func.sum(EmailSendCount.failed), 0),
        )
        .filter(
            EmailSendCount.occurrence_id == occurrence_id,
            EmailSendCount.channel == channel,
        )
        .one()
    )
    return int(row[0]), int(row[1])


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
