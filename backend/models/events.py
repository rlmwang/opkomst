from datetime import datetime
from typing import Literal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Event(UUIDMixin, TimestampMixin, Base):
    """One event row. ``archived_at`` flips for archive/restore;
    edits overwrite in place. The slug is unique across the
    table; archived events keep their slug (the public surface
    404s on archive — see ``test_public_archived.py``)."""

    __tablename__ = "events"

    # 8-char nanoid, public. Unique across all events; archive
    # doesn't free it because the slug may be in URLs the user
    # bookmarked, and restoring expects the slug to come back
    # unchanged.
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Optional list of "I can help with" tasks (e.g. opbouwen / afbreken).
    # Empty list means the question isn't shown on the public form.
    help_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    feedback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # When True, signups who leave an email get a single reminder
    # email roughly 3 days before the event starts (see
    # ``services.mail_lifecycle`` REMINDER channel).
    # Independent of the feedback toggle — both can be on,
    # both can be off.
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # ISO language tag — drives the public-page UI language and the
    # locale of the post-event feedback email. Two-letter codes
    # only ('nl' / 'en') today; widen the Literal to add a region.
    locale: Mapped[Literal["nl", "en"]] = mapped_column(Text, nullable=False, default="nl")
    created_by: Mapped[str] = mapped_column(
        Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    chapter_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("chapters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (Index("ix_events_archived_chapter", "archived_at", "chapter_id"),)


class Signup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "signups"

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    # Display name is optional — visitors can sign up anonymously,
    # leaving the organiser to count headcount from ``party_size`` only.
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ``source_choice`` is optional too. NULL means the visitor didn't
    # answer "how did you find us"; the organiser-side breakdown
    # excludes those.
    source_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Subset of the parent event's ``help_options`` the attendee opted
    # into (e.g. ["opbouwen"]). Empty when the event has no help_options
    # configured or the attendee skipped the question.
    help_choices: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # No email column on this table. The encrypted recipient address
    # lives on ``EmailDispatch.encrypted_email`` — one copy per
    # (signup, channel) row the email applies to. Absence of a
    # dispatch row for a (signup, channel) pair means "this channel
    # doesn't apply / never will" (no email at signup time, toggle
    # off, expired window, or retired by toggle-off cleanup); the
    # address physically can't exist without a row that intends to
    # use it.
