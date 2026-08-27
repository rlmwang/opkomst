from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..mixins import EditTokenMixin, OrgEntityMixin, TenantMixin, TimestampMixin, UUIDMixin


class Event(UUIDMixin, TimestampMixin, OrgEntityMixin, TenantMixin, Base):
    """The definition of an event — recurring or one-off. It holds the shared
    content and the recurrence rule; concrete dates are ``Occurrence`` rows,
    materialised over time by the tick. A one-off is ``cycle_slots == []``,
    with its single occurrence (on ``starts_on``) created at once.

    The recurrence rule is the chores roster's k-week cycle, reused: a
    ``period_weeks`` cycle length, a ``starts_on`` anchor, and ``cycle_slots``
    weekday offsets (``week*7 + weekday``, Mon=0), with the pure date math in
    ``services/recurrence.py``. Events add a shared wall-clock time of day
    (``start_time`` / ``end_time``) over the all-day roster.

    The public sign-up page is per occurrence (``Occurrence.slug``); the event
    row has no public page of its own. ``archived_at`` archives the whole
    event (all its occurrences); edits overwrite in place."""

    __tablename__ = "events"

    # Spine (slug, name_nl/name_en, image_url, image_artist_instagram,
    # locale, created_by, chapter_id, archived_at) comes from
    # OrgEntityMixin. The slug here is organiser-internal — the public slug
    # lives on Occurrence. ``topic`` is the bilingual richtext details body.
    topic_nl: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional location (free text) + resolved coordinates, the same
    # shape a datepoll and a roster carry: an online meeting or a spot
    # everyone already knows needs no address.
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The two optional questions on the public sign-up form, each with
    # its own switch. Off means the question isn't asked at all: the
    # public page never sees the options, and a submission carrying an
    # answer to it is refused. The options survive being switched off,
    # so turning a question back on brings the organiser's own list
    # back rather than an empty one.
    #
    # Every switch here starts off, mail and agenda listing included: an
    # event asks for a name and a headcount until its organiser says
    # otherwise.
    source_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    help_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    help_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    feedback_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Whether the public page insists on a (pseudo)name before it will
    # accept anything. Off by default: a name real or not is what the
    # contract offers, and a page that refuses an empty box asks for an
    # identity the organiser may not need. On when the answers are only
    # useful attached to somebody.
    name_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Whether somebody may reopen their own link and change what they
    # booked. On by default: plans change, and a sign-up nobody can
    # correct becomes a sign-up nobody cancels either. Off when the
    # headcount is being acted on and has to stop moving. Withdrawing
    # is never closed by it (``docs/design-edit-link.md``).
    answers_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    # The recurrence rule (roster's k-week cycle + a time of day).
    # ``starts_on`` sits inside cycle week 0 (which runs from the Monday of
    # its week, derived by ``recurrence.cycle_anchor_monday``) and is the
    # earliest date an occurrence may fall on. ``start_time`` / ``end_time`` are the shared
    # naive Europe/Amsterdam wall-clock time applied to every occurrence date.
    # ``period_weeks`` is the cycle length k (1 = weekly). ``cycle_slots`` are
    # the selected weekday offsets (``week*7 + weekday``, Mon=0, 0..7k-1);
    # ``[]`` means a one-off (a single occurrence on ``starts_on``).
    # ``span_weeks`` runs the pattern that many weeks from ``starts_on``;
    # NULL = open-ended (rolling). ``horizon_days`` bounds how far ahead the
    # tick materialises concrete occurrences.
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    period_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    cycle_slots: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    span_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90, server_default=text("90"))

    __table_args__ = (
        Index("ix_events_archived_chapter", "archived_at", "chapter_id"),
        CheckConstraint("num_nonnulls(name_nl, name_en) >= 1", name="ck_events_name_present"),
    )

    occurrences: Mapped[list["Occurrence"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Occurrence.starts_at",
    )


class Occurrence(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One materialised, dated instance of an ``Event``. It carries only what
    is genuinely its own: its concrete wall-clock datetimes (the pattern date
    + the event's time of day) and its own public sign-up slug. All content
    (name, location, questions, ...) is read through ``event_id`` — nothing is
    copied, so editing the event updates every occurrence at once. Its
    "sessie i van N" ordinal is not stored; it is the row's rank among the
    event's occurrences, derived at read time, so a rule edit that changes
    which dates recur can't leave a stale ordinal behind and can't strand a
    frozen past session without a number of its own."""

    __tablename__ = "occurrences"

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    # 8-char nanoid, the public URL (/e/{slug}). Unique across the table.
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # Naive wall-clock = on_date + event.start_time / end_time.
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "starts_at", name="uq_occurrences_event_starts_at"),
        Index("ix_occurrences_event_starts", "event_id", "starts_at"),
    )

    event: Mapped["Event"] = relationship(back_populates="occurrences")


class Registration(UUIDMixin, EditTokenMixin, TimestampMixin, TenantMixin, Base):
    """One person's booking against an event — the order header that groups
    the per-occurrence line items (``Signup``) made in one submission. It
    holds the single edit link, an optional pseudonym, and the party size.

    No email column. The encrypted recipient address lives only on the
    per-occurrence ``EmailDispatch`` rows, decoupled from this graph, so the
    booking can group a person's occurrences for their own edit page without
    ever linking to the email graph. ``edit_token_hash`` +
    ``link_recovered_at`` come from EditTokenMixin."""

    __tablename__ = "registrations"

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    signups: Mapped[list["Signup"]] = relationship(
        back_populates="registration",
        cascade="all, delete-orphan",
    )


class Signup(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """A line item: one booking (``registration_id``) attending one occurrence
    (``occurrence_id``). Headcount for an occurrence is ``SUM(party_size)``
    over the registrations of its line items. The optional ``source_choice``
    and ``help_choices`` are captured per line item (copied from the one
    submission onto each occurrence) so per-occurrence breakdowns stay exact.

    No email here — the address graph (``EmailDispatch``) keys on the
    occurrence and never references a line item or a registration."""

    __tablename__ = "signups"

    registration_id: Mapped[str] = mapped_column(
        Text, ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurrence_id: Mapped[str] = mapped_column(
        Text, ForeignKey("occurrences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    help_choices: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (UniqueConstraint("registration_id", "occurrence_id", name="uq_signups_registration_occurrence"),)

    registration: Mapped["Registration"] = relationship(back_populates="signups")
    occurrence: Mapped["Occurrence"] = relationship()
