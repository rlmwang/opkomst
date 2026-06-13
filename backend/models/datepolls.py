"""Datepolls — dates-only availability polls (the third public feature).

A ``Datepoll`` is an organiser-authored, chapter-scoped poll over a
set of candidate calendar dates (no time-slots). Anyone with the
slug picks yes/maybe/no per date and may leave a one-line comment per
date, under a self-chosen pseudonym (real or not). It is independent
of Events / Forms and sends no email.

Four tables:

* ``datepolls`` — one row per poll. ``archived_at`` for soft archive
  (mirrors Event/Form); a fresh slug per poll keeps the public URL
  bookmark-stable across restores.
* ``datepoll_dates`` — the candidate dates, one row each, unique per
  poll. Ordered by ``on_date``; no ordinal column (the date is its
  own order and its own natural key).
* ``datepoll_submissions`` — one row per fill-out. Holds the
  pseudonym (``display_name``, NULL = anonymous) and nothing else
  identifying. The submission shape rule (docs/principles-architecture
  §17): a parent row exists because there *is* per-submission data;
  Forms had none and so has no parent table.
* ``datepoll_responses`` — one row per (submission, date) the
  respondent answered. ``availability`` is the tri-state; ``comment``
  is an optional note on that date. Unanswered dates have no row.

Privacy: the only identifier is the self-chosen pseudonym, exactly as
``Signup.display_name``. No email, no encryption, no IP, no read-back
of a submission id.
"""

from datetime import date, datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Datepoll(UUIDMixin, TimestampMixin, Base):
    """One dates-only poll. ``archived_at`` flips for archive/restore;
    edits overwrite in place. The slug is unique across the table and
    stays attached across archive/restore (same as Event/Form)."""

    __tablename__ = "datepolls"

    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional 4:5 hero image (GitHub-hosted raw URL) + artist credit,
    # same shape and pipeline as Event (services/image.py).
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_artist_instagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ISO language tag — drives the public poll's UI language.
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

    # Mirrors the events/forms list index.
    __table_args__ = (Index("ix_datepolls_archived_chapter", "archived_at", "chapter_id"),)


class DatepollDate(UUIDMixin, TimestampMixin, Base):
    """One candidate date on one poll. ``on_date`` is a whole calendar
    date (no time, no tz) and is unique within the poll — it doubles
    as the natural key the edit diff matches on."""

    __tablename__ = "datepoll_dates"

    datepoll_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepolls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    on_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (UniqueConstraint("datepoll_id", "on_date", name="uq_datepoll_dates_poll_date"),)


class DatepollSubmission(UUIDMixin, TimestampMixin, Base):
    """One fill-out. ``display_name`` is the self-chosen pseudonym
    (NULL = anonymous); the row id is the opaque submission identifier
    that groups the per-date answers. Nothing resolves it back to a
    person beyond the pseudonym the respondent typed."""

    __tablename__ = "datepoll_submissions"

    datepoll_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepolls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SHA-256 of the respondent's secret edit-link token (raw never
    # stored, organiser never sees it). See ``services/edit_token.py``.
    edit_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True, index=True)


class DatepollResponse(UUIDMixin, TimestampMixin, Base):
    """One respondent's answer to one date. Exists only for an
    answered date; an unset date has no row. ``availability`` is
    constrained to the three tri-state values (CHECK backstop, the
    canonical set is the ``Availability`` literal in
    ``schemas/datepolls.py``)."""

    __tablename__ = "datepoll_responses"

    submission_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepoll_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    datepoll_date_id: Mapped[str] = mapped_column(
        Text, ForeignKey("datepoll_dates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    availability: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("submission_id", "datepoll_date_id", name="uq_datepoll_responses_submission_date"),
        CheckConstraint(
            "availability IN ('yes', 'no', 'maybe')",
            name="ck_datepoll_responses_availability",
        ),
    )
