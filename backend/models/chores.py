"""Recurring chores — the takenrooster feature (fourth public entity).

A ``Roster`` is an organiser-authored, chapter-scoped schedule of
recurring **chores**. Anyone with the slug enrols as a ``Volunteer``
(a self-chosen pseudonym, optionally an email), ticks the chores they
will do (``Enrollment``), and the system materialises dated ``Shift``
occurrences and assigns volunteers to them fairly. A volunteer marks a
shift done or hands it off from a token-based personal page; no account.

Recurrence is a **k-week cycle**, set once per roster (``period_weeks``).
A chore's ``cycle_slots`` are flat offsets into that cycle:
``offset = week_index*7 + weekday``, range ``0 .. 7*period_weeks - 1``,
**Mon=0** (Python ``date.weekday()``). For k=1 this collapses to the
plain weekday set ``0..6``. When k>1, cycle index 0 anchors on the first
Monday within the interval (derived from ``starts_on``, never stored) so
"week A / week B" means a concrete calendar week across the whole roster.
``services/recurrence.py::occurs_on`` is the single source of truth for
"does a chore fall on a date".

Five tables:

* ``rosters`` — one row per schedule. Spine (slug/name/image/locale/
  created_by/chapter_id/archived_at) from ``OrgEntityMixin``; recurrence
  bounds (``period_weeks``, ``starts_on``, ``ends_on``) and reminder
  settings are roster-specific.
* ``chores`` — the recurring tasks, ordered, each with its ``cycle_slots``
  and ``people_per_shift``.
* ``volunteers`` — public enrolments. ``encrypted_email`` is the only PII,
  long-lived AES-GCM ciphertext (design §6), nulled on mute/leave; the
  ``edit_token_hash`` (SHA-256, raw never stored) keys the personal page.
* ``enrollments`` — volunteer ↔ chore opt-in, composite PK (mirrors
  ``user_chapters``).
* ``shifts`` — one materialised ``(chore, date, slot_index)`` occurrence
  with an assignee and a status. ``volunteer_id`` is ``SET NULL`` so a
  volunteer leaving preserves completion history anonymously.
"""

from datetime import date, datetime
from typing import Literal

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
    LargeBinary,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import EditTokenMixin, OrgEntityMixin, TenantMixin, TimestampMixin, UUIDMixin


class Roster(UUIDMixin, TimestampMixin, OrgEntityMixin, TenantMixin, Base):
    """One chore roster. ``archived_at`` flips for archive/restore; edits
    overwrite in place. The slug is unique across the table and stays
    attached across archive/restore (same as Event/Form/Datepoll)."""

    __tablename__ = "rosters"

    # Spine (slug, name_nl/name_en, image_url, image_artist_instagram,
    # locale, created_by, chapter_id, archived_at) comes from
    # OrgEntityMixin. ``description`` is the bilingual richtext details body.
    description_nl: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether the public page insists on a (pseudo)name before it will
    # accept anything. Off by default: a name real or not is what the
    # contract offers, and a page that refuses an empty box asks for an
    # identity the organiser may not need. On when the answers are only
    # useful attached to somebody.
    name_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Optional location (free text) + resolved coordinates, same optional
    # shape as Datepoll — chores often have a fixed venue but needn't.
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Recurrence cycle length k, set once for every chore in the roster.
    # k=1 is plain weekly. When k>1, cycle index 0 anchors on the first
    # Monday on/after ``starts_on`` (derived) and ``cycle_slots`` span [0, 7*k).
    period_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ``starts_on`` bounds the earliest date shifts may be generated and
    # anchors the k>1 cycle; ``ends_on`` NULL = open-ended (rolling horizon).
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # How many days before a shift the assignee is reminded. Shifts are
    # date-only (no clock time), so this is days-before, sent at a fixed
    # civil local hour (see services/mail_lifecycle, task 08).
    reminder_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # How far ahead the schedule is pinned and reliable. Occurrences within
    # [today, today+commit_horizon_days] are materialised as Shift rows and
    # never reshuffle; beyond it the schedule is a tentative projection.
    # Must be >= reminder_days_before (validated in the schema).
    commit_horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, default=21)
    # Lifecycle gate: NULL = forming (draft, nothing pinned/promised), set
    # = running (the tick pins the commit horizon). One-way.
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # The organiser's list: one tenant, the chapters its user
        # belongs to, newest first, with the ordering column in the
        # index so the planner stops at the page instead of sorting.
        Index("ix_rosters_tenant_chapter_created", "tenant_id", "chapter_id", "created_at"),
        Index("ix_rosters_archived_chapter", "archived_at", "chapter_id"),
        CheckConstraint("num_nonnulls(name_nl, name_en) >= 1", name="ck_rosters_name_present"),
    )


class Chore(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One recurring task on one roster. ``ordinal`` drives display order
    (re-numbered 1..N on every update). ``cycle_slots`` are flat offsets
    into the roster's k-week cycle (``week*7 + weekday``, 0..7k-1, Mon=0);
    ``people_per_shift`` > 1 materialises that many Shift rows per date."""

    __tablename__ = "chores"

    roster_id: Mapped[str] = mapped_column(
        Text, ForeignKey("rosters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_slots: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    people_per_shift: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Optional emoji icon for the chore (rendered on the public page).
    emoji: Mapped[str | None] = mapped_column(Text, nullable=True)


class Volunteer(UUIDMixin, EditTokenMixin, TimestampMixin, TenantMixin, Base):
    """One public enrolment. ``display_name`` is the self-chosen pseudonym
    (NULL = anonymous). ``encrypted_email`` is the optional, long-lived
    AES-GCM ciphertext of the email (design §6) — nulled on mute/leave,
    decrypted only by the lifecycle worker. ``edit_token_hash`` is the
    SHA-256 of the secret personal-page token (raw never stored)."""

    __tablename__ = "volunteers"

    roster_id: Mapped[str] = mapped_column(
        Text, ForeignKey("rosters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_email: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_reminders: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The volunteer's own language (the flag active at join; falls back to
    # the roster's primary locale). Drives the reminder email's language and
    # which side of the bilingual roster content it renders.
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="nl", server_default=text("'nl'"))
    # ``edit_token_hash`` + ``link_recovered_at`` come from EditTokenMixin.


class Enrollment(TimestampMixin, TenantMixin, Base):
    """Volunteer ↔ Chore opt-in. Composite PK ``(volunteer_id, chore_id)``
    enforces one row per pair; both FKs cascade on hard-delete (mirrors
    ``user_chapters``)."""

    __tablename__ = "enrollments"

    volunteer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chore_id: Mapped[str] = mapped_column(Text, ForeignKey("chores.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (PrimaryKeyConstraint("volunteer_id", "chore_id", name="pk_enrollments"),)


class VolunteerAvailability(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """A date range one volunteer is unavailable. Fed into the projection
    and the pin step so an away volunteer is excluded from occurrences on
    those dates (design §7 availability). Ranges are inclusive."""

    __tablename__ = "volunteer_availability"

    volunteer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)


class Shift(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One materialised ``(chore, date, slot_index)`` occurrence. ``status``
    is the lifecycle: ``open`` (unassigned / up for grabs), ``scheduled``
    (assigned), ``done``, ``missed``. ``volunteer_id`` is ``SET NULL`` so a
    volunteer leaving keeps past shifts for anonymous completion stats and
    drops future ones back to ``open`` on the next tick."""

    __tablename__ = "shifts"

    # No ``index=True``: ``(chore_id, on_date)`` below leads with it.
    chore_id: Mapped[str] = mapped_column(Text, ForeignKey("chores.id", ondelete="CASCADE"), nullable=False)
    on_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    volunteer_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("volunteers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[Literal["scheduled", "done", "open", "missed"]] = mapped_column(Text, nullable=False, default="open")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("chore_id", "on_date", "slot_index", name="uq_shifts_chore_date_slot"),
        CheckConstraint(
            "status IN ('scheduled', 'done', 'open', 'missed')",
            name="ck_shifts_status",
        ),
        Index("ix_shifts_chore_date", "chore_id", "on_date"),
    )


class ShiftEvent(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """Append-only accountability log: one row per volunteer action or
    outcome on a shift. The mutable Shift row loses history the moment a
    shift is handed off or reassigned (``volunteer_id`` is overwritten),
    so this captures the *semantics* stats need — who did what — that a
    state row can't. Rows die with the roster or the volunteer (CASCADE);
    ``shift_id`` is SET NULL so deleting a shift keeps the fact.

    Kinds (design §7 provenance): ``assigned`` (WRH-assigned by the tick),
    ``claimed`` (took an open shift), ``covered`` (took over another's
    confirmed shift), ``inherited`` (force-assigned a departed volunteer's
    shift — task 13), ``completed``, ``deferred`` (passed), ``missed`` (a
    scheduled shift they held passed undone)."""

    __tablename__ = "shift_events"

    roster_id: Mapped[str] = mapped_column(
        Text, ForeignKey("rosters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volunteer_id: Mapped[str] = mapped_column(
        Text, ForeignKey("volunteers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[str | None] = mapped_column(Text, ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[Literal["assigned", "claimed", "covered", "inherited", "completed", "deferred", "missed"]] = (
        mapped_column(Text, nullable=False)
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('assigned', 'claimed', 'covered', 'inherited', 'completed', 'deferred', 'missed')",
            name="ck_shift_events_kind",
        ),
    )
