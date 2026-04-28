"""One row per (signup, channel) email send attempt.

Replaces the per-channel column triplets that used to live on
``Signup`` itself (``feedback_email_status`` /
``feedback_message_id`` / ``feedback_sent_at`` and the reminder
parallel set). The normalised shape:

* makes adding a new channel a config change rather than a
  schema migration plus parallel code paths;
* gives the bounce webhook a single indexed lookup on
  ``message_id`` instead of "try column A, then column B";
* lets the privacy-wipe rule become a single SQL existence
  check rather than a per-column status comparison;
* removes the ``not_applicable`` status entirely — that state is
  now represented by the absence of a dispatch row.

A signup gains a dispatch row only when the corresponding
channel is going to fire (toggle on, email present, event
window viable). Toggle-off and expired-window cleanup *delete*
rows rather than retiring them to a sentinel status — there is
no audit-history requirement here."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index, Text, UniqueConstraint
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
    * ``sent`` — successfully handed to SMTP.
    * ``failed`` — every retry exhausted (or decrypt failed; see
      ``services.email_dispatcher``).
    * ``bounced`` — Scaleway TEM webhook reported a hard bounce
      after a successful send.
    * ``complaint`` — recipient flagged the message as spam.
    """

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"


class SignupEmailDispatch(UUIDMixin, TimestampMixin, Base):
    """One per (signup, channel). Created at signup time when the
    channel applies; updated by the worker as the lifecycle
    progresses; deleted by the reaper / toggle-off cleanup when
    the channel no longer applies."""

    __tablename__ = "signup_email_dispatches"

    # Points at Signup.id (signups are not SCD2). No FK in code
    # because we deliberately keep the dispatch "loosely coupled"
    # — the worker queries it standalone.
    signup_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    channel: Mapped[EmailChannel] = mapped_column(
        SAEnum(EmailChannel, name="email_channel", native_enum=True),
        nullable=False,
    )
    status: Mapped[EmailStatus] = mapped_column(
        SAEnum(EmailStatus, name="email_status", native_enum=True),
        nullable=False,
        default=EmailStatus.PENDING,
    )
    # Pre-minted before the SMTP call so a process crash mid-send
    # leaves the row recoverable by the boot-time reaper. Indexed
    # for the bounce/complaint webhook lookup.
    message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # One dispatch per (signup, channel) — the worker's
        # claim-by-conditional-UPDATE relies on this uniqueness
        # to avoid races.
        UniqueConstraint("signup_id", "channel", name="uq_dispatches_signup_channel"),
        # Webhook lookup. Sparse — most rows have a message_id
        # but failed-pre-send rows don't.
        Index("ix_dispatches_message_id", "message_id"),
        # Worker sweep filter — covers the
        # ``WHERE channel = ? AND status = 'pending'`` predicate.
        Index("ix_dispatches_channel_status", "channel", "status"),
    )
