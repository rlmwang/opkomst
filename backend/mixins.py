from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship
from uuid_utils import uuid7

if TYPE_CHECKING:
    from .models.tenants import Tenant


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid7_str() -> str:
    return str(uuid7())


def _current_tenant() -> str:
    """Column default for ``tenant_id``. Imported lazily so the models
    package doesn't pull the services package at import time."""
    from .services.tenancy import current

    return current()


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


class TenantMixin:
    """The owning tenant, on every table without exception.

    For a root row (a chapter, a user, an event) this is the fact
    itself. For a child row (an occurrence, a signup, a shift event) it
    is denormalized from the parent, deliberately: every read filter,
    every uniqueness index and every "could this leak across tenants"
    question then reduces to one predicate on the row in front of you,
    with no join to get wrong.

    Denormalization needs a guard, and it has two, in
    ``tests/test_tenancy.py``: one asserts the column exists on every
    mapped table, the other walks the foreign keys and asserts a child
    never disagrees with its parent.

    The value defaults to the tenant bound to the current context (see
    ``services.tenancy``), so an insert doesn't have to name it and
    can't quietly omit it — a write with no tenant in scope raises
    rather than guessing."""

    @declared_attr
    def tenant_id(cls) -> Mapped[str]:
        return mapped_column(
            Text,
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            default=_current_tenant,
        )

    @declared_attr
    def tenant(cls) -> Mapped["Tenant"]:
        """The owning organisation. Loaded when a surface needs the slug
        — the brand a page or an email wears — rather than the id."""
        return relationship("Tenant", lazy="select", viewonly=True)


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

    Each such entity carries a public ``slug``, a bilingual title
    (``name_nl`` / ``name_en``), an optional 4:5 hero image + artist
    credit, a ``locale`` naming the primary language (the public page's
    default view and fallback anchor), the creating organiser, the owning
    chapter, and an ``archived_at`` soft-archive flag.

    Title and description are authored in both Dutch and English; either
    language falls back to the other when empty. Both ``name_*`` columns
    are nullable, with a per-table CHECK (``ck_{table}_name_present``)
    guaranteeing at least one is set — the primary-language one is
    required at the schema boundary.

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

    # Bilingual title. Both nullable; the per-table CHECK requires at
    # least one, and the schema requires the primary-language one.
    @declared_attr
    def name_nl(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    @declared_attr
    def name_en(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    # Where the entity's 4:5 hero image is stored, as a path inside the
    # image host: ``events/{id}/{timestamp}.jpg``. Not a URL. The URL
    # anyone sees is this app's own (``/i/{path}``, built by
    # ``services/image.public_url``), so nothing rendered anywhere says
    # where the bytes actually live. Null = pages render without a hero
    # and the OG card falls back to the favicon.
    @declared_attr
    def image_path(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    # Instagram handle of the hero-image artist (the credit line),
    # stored without the leading ``@``. Null = no caption rendered.
    @declared_attr
    def image_artist_instagram(cls) -> Mapped[str | None]:
        return mapped_column(Text, nullable=True)

    # Primary language: the public page's default view + fallback anchor,
    # and the email language for organiser-driven sends without a per-
    # recipient locale. Two-letter codes only ('nl' / 'en') today; widen
    # the Literal to add a region.
    @declared_attr
    def locale(cls) -> Mapped[Literal["nl", "en"]]:
        return mapped_column(Text, nullable=False, default="nl")

    # No index. A foreign key is not indexed by Postgres automatically,
    # and the reasons to add one are a query that follows it or a cascade
    # that deletes by it. Neither applies: nothing outside the seed
    # filters an entity by who made it, and the FK is ``SET NULL``, which
    # a full scan handles once in the life of a deleted user.
    @declared_attr
    def created_by(cls) -> Mapped[str]:
        return mapped_column(Text, ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

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
