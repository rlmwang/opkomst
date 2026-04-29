from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import SCD2Mixin, TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, SCD2Mixin, Base):
    """SCD2 dimension. JWT ``sub`` is ``user.entity_id`` so tokens
    survive every edit (rename, role change, approval, chapter
    reassignment). Email uniqueness is enforced via a partial unique
    index over current versions — multiple history rows can share
    the same email for one logical account."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="organiser")
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Points at Chapter.entity_id; no FK because Chapter is SCD2.
    chapter_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    __table_args__ = (
        Index(
            "uq_users_email_current",
            "email",
            unique=True,
            postgresql_where=text("valid_until IS NULL"),
        ),
    )


class LoginToken(UUIDMixin, TimestampMixin, Base):
    """One-shot magic-link token. Issued on /auth/login-link, redeemed
    on /auth/login. Single-use; deleted on redeem."""

    __tablename__ = "login_tokens"

    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    # Points at ``User.entity_id`` (SCD2 stable id).
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
