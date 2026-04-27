from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, LargeBinary, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import SCD2Mixin, TimestampMixin, UUIDMixin


class Event(UUIDMixin, TimestampMixin, SCD2Mixin, Base):
    """SCD2 dimension. See ``mixins.SCD2Mixin`` for the chain semantics
    and ``services.scd2`` for the helpers. ``EventOut.id =
    event.entity_id``; clients never see the per-version row id."""

    __tablename__ = "events"

    # 8-char nanoid, public — copies forward across versions. Partial
    # unique on current versions only (multiple history rows share a
    # slug for one logical event).
    slug: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Optional list of "I can help with" tasks (e.g. opbouwen / afbreken).
    # Empty list means the question isn't shown on the public form.
    help_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    questionnaire_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # When True, signups who leave an email get a single reminder
    # email roughly 3 days before the event starts (see
    # ``services.reminder_worker``). Independent of the
    # questionnaire toggle — both can be on, both can be off.
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ISO language tag — drives the public-page UI language and the
    # locale of the post-event feedback email. Two-letter codes
    # only ('nl' / 'en') today; widen to a code/region pair if we
    # ever localise per region.
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="nl")
    # Points at User.entity_id; no FK because user is also SCD2 (its
    # entity_id isn't unique across all rows).
    created_by: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # Points at Chapter.entity_id; no FK for the same reason.
    chapter_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    __table_args__ = (
        Index(
            "uq_events_slug_current",
            "slug",
            unique=True,
            sqlite_where=text("valid_until IS NULL"),
            postgresql_where=text("valid_until IS NULL"),
        ),
    )


class Signup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "signups"

    # Points at Event.entity_id (stable logical id), not row id.
    event_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
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
    encrypted_email: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    feedback_email_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_applicable", index=True
    )
    feedback_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    feedback_message_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    # Parallel set of fields tracking the 3-days-before reminder.
    # ``reminder_email_status`` mirrors the lifecycle of the
    # feedback status (not_applicable / pending / sent / bounced /
    # complaint / failed). ``encrypted_email`` is wiped only after
    # *every* pending email activity finishes (see
    # ``services.email_lifecycle._wipe_if_done``).
    reminder_email_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_applicable", index=True
    )
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminder_message_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
