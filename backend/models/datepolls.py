"""Datepolls — date + time-slot availability polls (the third public
feature).

A ``Datepoll`` is an organiser-authored, chapter-scoped poll over a
set of candidate **slots**. A slot is a calendar date with an optional
time range: ``(on_date, start_time, end_time)``. When the times are
NULL the slot is the whole day — so a poll with only whole-day slots
is the original dates-only Doodle, and time-slots are a pure
generalisation (no separate code path, no discriminator). Anyone with
the slug picks yes/maybe/no per slot and may leave one optional note
on the whole submission, under a self-chosen pseudonym (real or not).
It is independent of Events / Forms and sends no email.

Four tables:

* ``datepolls`` — one row per poll. ``archived_at`` for soft archive
  (mirrors Event/Form); a fresh slug per poll keeps the public URL
  bookmark-stable across restores.
* ``datepoll_slots`` — the candidate slots, one row each. The natural
  key is ``(on_date, start_time, end_time)``, unique per poll
  (``NULLS NOT DISTINCT`` so a day has at most one whole-day slot).
  Ordered by ``on_date`` then ``start_time`` (whole-day first).
* ``datepoll_submissions`` — one row per fill-out. Holds the
  pseudonym (``display_name``, NULL = anonymous) and the optional
  whole-submission ``note``, nothing else identifying. The submission
  shape rule (docs/principles-architecture §17): a parent row exists
  because there *is* per-submission data; Forms had none and so has no
  parent table.
* ``datepoll_responses`` — one row per (submission, slot) the
  respondent answered. ``availability`` is the tri-state. Unanswered
  slots have no row.

Privacy: the only identifier is the self-chosen pseudonym, exactly as
``Signup.display_name``. No email, no encryption, no IP, no read-back
of a submission id.
"""

from datetime import date, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import EditTokenMixin, OrgEntityMixin, TenantMixin, TimestampMixin, UUIDMixin


class Datepoll(UUIDMixin, TimestampMixin, OrgEntityMixin, TenantMixin, Base):
    """One dates-only poll. ``archived_at`` flips for archive/restore;
    edits overwrite in place. The slug is unique across the table and
    stays attached across archive/restore (same as Event/Form)."""

    __tablename__ = "datepolls"

    # Spine (slug, name, image_url, image_artist_instagram, locale,
    # created_by, chapter_id, archived_at) comes from OrgEntityMixin.
    description_nl: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether the public page insists on a (pseudo)name before it will
    # accept anything. Off by default: a name real or not is what the
    # contract offers, and a page that refuses an empty box asks for an
    # identity the organiser may not need. On when the answers are only
    # useful attached to somebody.
    name_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Whether somebody may reopen their own link and change what they
    # answered. On by default: plans change, and an answer nobody can
    # correct is an answer nobody updates when their week changes. Off
    # once the date is being picked and the answers have to stop moving.
    # Withdrawing is never closed by it (``docs/design-edit-link.md``).
    answers_editable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    # Optional location (free text) + resolved coordinates, same shape
    # as Event — but optional here, since a poll often settles the time
    # before the place. Coords drive the public map link.
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Mirrors the events/forms list index.
    __table_args__ = (
        # The organiser's list: one tenant, the chapters its user
        # belongs to, newest first, with the ordering column in the
        # index so the planner stops at the page instead of sorting.
        Index("ix_datepolls_tenant_chapter_created", "tenant_id", "chapter_id", "created_at"),
        Index("ix_datepolls_archived_chapter", "archived_at", "chapter_id"),
        CheckConstraint("num_nonnulls(name_nl, name_en) >= 1", name="ck_datepolls_name_present"),
    )


class DatepollSlot(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One candidate slot on one poll: a date with an optional time
    range. ``start_time``/``end_time`` are both NULL for a whole-day
    slot, or both set for a timed slot (the schema enforces
    both-or-neither and ``end > start``). The triple
    ``(on_date, start_time, end_time)`` is the natural key the edit
    diff matches on; ``NULLS NOT DISTINCT`` makes the whole-day slot
    unique per day rather than treating each NULL pair as distinct."""

    __tablename__ = "datepoll_slots"

    datepoll_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepolls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    on_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "datepoll_id",
            "on_date",
            "start_time",
            "end_time",
            name="uq_datepoll_slots_poll_slot",
            postgresql_nulls_not_distinct=True,
        ),
    )


class DatepollSubmission(UUIDMixin, EditTokenMixin, TimestampMixin, TenantMixin, Base):
    """One fill-out. ``display_name`` is the self-chosen pseudonym
    (NULL = anonymous); the row id is the opaque submission identifier
    that groups the per-date answers. Nothing resolves it back to a
    person beyond the pseudonym the respondent typed."""

    __tablename__ = "datepoll_submissions"

    datepoll_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepolls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # One optional free-text note on the whole submission (NULL = none).
    # Replaces the old per-date comment now that a submission spans
    # multiple slots — one note per respondent, not one per slot.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ``edit_token_hash`` + ``link_recovered_at`` come from EditTokenMixin.


class DatepollResponse(UUIDMixin, TimestampMixin, TenantMixin, Base):
    """One respondent's answer to one slot. Exists only for an
    answered slot; an unset slot has no row. ``availability`` is
    constrained to the three tri-state values (CHECK backstop, the
    canonical set is the ``Availability`` literal in
    ``schemas/datepolls.py``)."""

    __tablename__ = "datepoll_responses"

    submission_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepoll_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    datepoll_slot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepoll_slots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    availability: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("submission_id", "datepoll_slot_id", name="uq_datepoll_responses_submission_slot"),
        CheckConstraint(
            "availability IN ('yes', 'no', 'maybe')",
            name="ck_datepoll_responses_availability",
        ),
    )
