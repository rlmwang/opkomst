"""One row per (event, channel, attendee) email send attempt.

Decoupled from ``Signup``: the email subsystem hangs off
``Event``, never references the survey-data subsystem. Two
independent graphs share an event:

* signup-side — display_name, party_size, source_choice,
  help_choices. Permanent record of who turned up.
* email-side — encrypted_email, channel, status, message_id.
  Ephemeral — rows finalise, addresses null, rows delete.

A row is created at public-signup time when the channel applies
(toggle on, email given, event window viable); the worker
updates it as the lifecycle progresses; reapers / toggle-off
cleanup delete it when the channel no longer applies. No row
anywhere in the database links a signup record to its email
address; the privacy contract is structural, not policed.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class EmailChannel(StrEnum):
    """Which kind of email a dispatch row represents."""

    REMINDER = "reminder"
    FEEDBACK = "feedback"


class EmailStatus(StrEnum):
    """Lifecycle of a single dispatch.

    * ``pending`` — the worker hasn't picked it up yet, or has
      pre-minted a message_id and is mid-send.
    * ``sent`` — successfully handed to SMTP. Terminal.
    * ``failed`` — every retry exhausted (or decrypt failed; see
      ``services.mail_lifecycle``). Terminal.

    There's no ``bounced`` / ``complaint`` here. We don't ingest
    delivery feedback: the SMTP provider's own dashboard is the
    source of truth for reputation. Stripping the path also drops
    the Scaleway webhook + Cockpit-topic dependency that was
    starting to cost real money for a near-no-op feature."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class EmailDispatch(UUIDMixin, TimestampMixin, Base):
    """One per (event, channel, attendee). Created at public-signup
    time when the channel applies; updated by the worker as the
    lifecycle progresses; deleted by the reapers / toggle-off
    cleanup when the channel no longer applies.

    No ``signup_id`` column. The dispatch carries the email work
    against an event; the signup record carries the survey
    answers. They live next to each other, never linked."""

    __tablename__ = "email_dispatches"

    event_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[EmailChannel] = mapped_column(
        SAEnum(EmailChannel, name="email_channel", native_enum=True),
        nullable=False,
    )
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="email_status", native_enum=True),
        nullable=False,
        default=EmailStatus.PENDING,
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
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Worker sweep filter — covers the
        # ``WHERE event_id = ? AND channel = ? AND status = 'pending'``
        # predicate used by run_for_event and the scope filters.
        Index("ix_dispatches_event_channel_status", "event_id", "channel", "status"),
    )
