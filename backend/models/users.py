from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, PrimaryKeyConstraint, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .chapters import Chapter


class User(UUIDMixin, TimestampMixin, Base):
    """One row per logical user. JWT ``sub`` is ``user.id``.

    Soft-delete via ``deleted_at`` — set to a timestamp when an
    admin removes the user; cleared when the user re-registers
    with the same email (the partial-unique index excludes
    soft-deleted rows so the slot frees up). Admin-driven changes
    surface as structured log lines (``logger.info("user_approved",
    ...)`` etc.) rather than relational audit rows; the log
    aggregator is the source of truth for who did what when.

    Chapter membership is many-to-many via ``user_chapters``.
    The ``chapters`` relationship returns every membership row's
    chapter regardless of soft-delete state — the admin DTO + the
    access-control helpers filter on ``Chapter.deleted_at IS NULL``
    at read time so a soft-deleted chapter being restored still
    finds its previous members intact."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="organiser")
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    chapters: Mapped[list["Chapter"]] = relationship(  # noqa: F821
        secondary="user_chapters",
        lazy="selectin",
    )

    __table_args__ = (
        # Email is unique across live users only — soft-deleted rows
        # don't block re-registration with the same address (that's
        # how restore works).
        Index(
            "uq_users_email_live",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class UserChapter(TimestampMixin, Base):
    """User ↔ Chapter membership row.

    Composite PK ``(user_id, chapter_id)`` enforces uniqueness; an
    accidental double-insert from a race becomes an
    ``IntegrityError`` we catch in ``services.user_chapters``.
    Both FKs cascade on hard-delete (delete the user or
    hard-delete the chapter and the membership goes with it).
    Chapter soft-delete (``Chapter.deleted_at``) is preserved on
    purpose: restoring an archived chapter brings its previous
    members back without an admin re-assignment step."""

    __tablename__ = "user_chapters"

    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[str] = mapped_column(
        Text, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (PrimaryKeyConstraint("user_id", "chapter_id", name="pk_user_chapters"),)


class LoginToken(UUIDMixin, TimestampMixin, Base):
    """One-shot magic-link token. Issued on /auth/login-link, redeemed
    on /auth/login. Single-use; deleted on redeem."""

    __tablename__ = "login_tokens"

    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RegistrationToken(UUIDMixin, TimestampMixin, Base):
    """One-shot "finish creating your account" token. Issued by
    /auth/login-link when an unknown email is submitted, redeemed
    by /auth/complete-registration with a user-supplied name. The
    token is the only thing tying the email to the future user row;
    no User exists yet at this stage.

    Single outstanding token per email: a fresh /auth/login-link
    for the same unknown email deletes any prior row before
    minting a new one, so only the most recent link in a user's
    inbox works. Deleted on successful redemption; reaped daily
    once expired."""

    __tablename__ = "registration_tokens"

    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
