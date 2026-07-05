from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from uuid_utils import uuid7


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid7_str() -> str:
    return str(uuid7())


class UUIDMixin:
    @declared_attr
    def id(cls) -> Mapped[str]:
        return mapped_column(Text, primary_key=True, default=_uuid7_str)


class EditTokenMixin:
    """The magic-link columns shared by every public submission row
    (Signup, FormSubmission, DatepollSubmission, Volunteer).

    ``edit_token_hash`` is the SHA-256 of the secret edit-link token —
    the raw token is never stored and the organiser never sees it (see
    ``services/edit_token.py``). ``link_recovered_at`` is stamped every
    time an organiser recovers the link (``edit_token.recover`` mints a
    fresh token over the old hash) and is never cleared: non-NULL means
    "an organiser has held this row's secret link at least once", which
    permanently drives the notice banner on the public edit page."""

    @declared_attr
    def edit_token_hash(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True, unique=True, index=True)

    @declared_attr
    def link_recovered_at(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True), nullable=True)


class TimestampMixin:
    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class OrgEntityMixin:
    """Shared spine for the organiser-owned, chapter-scoped, archivable
    top-level entities (Event, Form, Datepoll, Roster).

    Each such entity carries a public ``slug``, a ``name``, an optional
    4:5 hero image + artist credit, a ``locale`` driving the public-page
    UI (and, where applicable, email) language, the creating organiser,
    the owning chapter, and an ``archived_at`` soft-archive flag.

    Entity-specific columns (event times, datepoll slots, form
    questions, chore recurrence, ...) and the per-table
    ``ix_{table}_archived_chapter`` composite index stay on each model —
    the index embeds the table name, so it can't live here."""

    # 8-char nanoid, public. Unique across the table; archive doesn't
    # free it because the slug may be in URLs the user bookmarked, and
    # restoring expects the slug to come back unchanged.
    @declared_attr
    def slug(cls) -> Mapped[str]:
        return mapped_column(Text, nullable=False, unique=True, index=True)

    @declared_attr
    def name(cls) -> Mapped[str]:
        return mapped_column(Text, nullable=False)

    # Public URL of the entity's 4:5 hero image (GitHub-hosted raw URL;
    # uploads go through ``services/image.py``). Null = pages render
    # without a hero and the OG card falls back to the favicon.
    @declared_attr
    def image_url(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    # Instagram handle of the hero-image artist (the credit line),
    # stored without the leading ``@``. Null = no caption rendered.
    @declared_attr
    def image_artist_instagram(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    # ISO language tag — drives the public-page UI language. Two-letter
    # codes only ('nl' / 'en') today; widen the Literal to add a region.
    @declared_attr
    def locale(cls) -> Mapped[Literal["nl", "en"]]:
        return mapped_column(Text, nullable=False, default="nl")

    @declared_attr
    def created_by(cls) -> Mapped[str]:
        return mapped_column(Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)

    @declared_attr
    def chapter_id(cls) -> Mapped[str | None]:
        return mapped_column(
            Text,
            ForeignKey("chapters.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )

    @declared_attr
    def archived_at(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True), nullable=True, index=True)
