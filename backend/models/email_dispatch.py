"""One row per (event, channel, attendee) email still to send.

Decoupled from ``Signup``: the email subsystem hangs off
``Event``, never references the survey-data subsystem. Two
independent graphs share an event:

* signup-side — display_name, party_size, source_choice,
  help_choices. Permanent record of who turned up.
* email-side — encrypted_email, channel, message_id. Work, not
  history: a row exists because an email is owed, and stops
  existing the moment it is not.

A row is created at public-signup time when the channel applies
(toggle on, email given, event window viable) and is deleted when
the send finishes, one way or the other. Deleting rather than
finalising is what keeps the address' lifetime equal to the work's:
there is no state in which a row exists and its reason to exist does
not. It also keeps this table the size of the queue rather than the
size of everything ever sent, so the hourly sweeps read a handful of
rows however much mail the app has sent.

What is kept is a count. ``EmailSendCount`` holds one row per
(occurrence, channel, day) with how many sends succeeded and how
many failed. It is what the organiser page shows and what the daily
send cap counts against. It has no address and no identity.

No row anywhere in the database links a signup record to its email
address; the privacy contract is structural, not policed.
"""

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, Integer, LargeBinary, Text, UniqueConstraint, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TenantMixin, TimestampMixin, UUIDMixin


class EmailChannel(StrEnum):
    """Which kind of email a dispatch row represents."""

    REMINDER = "reminder"
    FEEDBACK = "feedback"


class EmailDispatch(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One per (occurrence, channel, attendee). Created at public-signup
    time when the channel applies; updated by the worker as the
    lifecycle progresses; deleted by the reapers / toggle-off
    cleanup when the channel no longer applies.

    Keyed on the occurrence, because reminders and feedback fire per
    occurrence date. No ``signup_id``/``registration_id`` column: the
    dispatch carries the email work against an occurrence; the sign-up line
    items carry the survey answers. They live next to each other, never
    linked."""

    __tablename__ = "email_dispatches"

    # No ``index=True``: ``(occurrence_id, channel)`` below leads with it.
    occurrence_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("occurrences.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[EmailChannel] = mapped_column(
        SAEnum(EmailChannel, name="email_channel", native_enum=True),
        nullable=False,
    )
    # AES-GCM-encrypted recipient address. Set at signup time when
    # the channel applies; nulled by ``_finalise`` on every terminal
    # transition (sent / failed); deleted with the row by the
    # reapers. The privacy contract — "we don't keep addresses
    # past the email we needed them for" — is exactly this row's
    # lifecycle: row exists ⇒ address exists; row finalises ⇒
    # address nulled in the same UPDATE; row deleted ⇒ address
    # deleted with it. No cross-table existence check, no separate
    # wipe pass, no link from a signup record to an address.
    encrypted_email: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Pre-minted before the SMTP call so a process crash mid-send
    # leaves the row recoverable by the boot-time reaper. Also
    # ends up on the outbound ``Message-ID:`` header so log lines
    # stay correlatable end-to-end.
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The recipient's own language, captured from the flag they had active
    # at sign-up (falls back to the event's primary locale). Drives both
    # the template language and which side of the bilingual event content
    # this email renders — so each attendee is mailed in the language they
    # engaged in, not the event's primary one.
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="nl", server_default=text("'nl'"))

    __table_args__ = (
        # ``WHERE occurrence_id = ? AND channel = ?``, which is what
        # run_for_occurrence and the toggle-off cleanup ask. The table
        # only ever holds outstanding work, so the sweeps that filter on
        # channel alone read a short table and need no index of their own.
        Index("ix_dispatches_occurrence_channel", "occurrence_id", "channel"),
    )


class EmailSendCount(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """How many emails of one channel went out for one occurrence on one
    day, and how many did not.

    The dispatch row is deleted when its send finishes, so this is what
    is left: two integers. It is what the organiser page counts and what
    the personal-account daily send cap is measured against, which is
    why the day is part of the key — a cap over a rolling window needs
    to know when, and a total needs to know nothing else.

    A day is as precise as it gets on purpose. It is deliberately
    incapable of being a delivery log: no address, no recipient, no
    per-send row, nothing that could reconstruct who was mailed.

    Incremented in the same transaction that deletes the dispatch, so
    the count and the queue cannot disagree."""

    __tablename__ = "email_send_counts"

    occurrence_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[EmailChannel] = mapped_column(
        SAEnum(EmailChannel, name="email_channel", native_enum=True),
        nullable=False,
    )
    # UTC, matching the send cap's window and the reapers' clock.
    day: Mapped[date] = mapped_column(Date, nullable=False)
    sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        # One row per pair; the increment is an upsert onto it.
        UniqueConstraint("occurrence_id", "channel", "day", name="uq_email_send_counts_occurrence_channel_day"),
        # The personal-account daily cap: everything this tenant sent
        # since a date. Two separate indexes make the planner combine
        # bitmaps; this answers it in one.
        Index("ix_email_send_counts_tenant_day", "tenant_id", "day"),
    )
