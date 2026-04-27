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
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="organiser")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Points at Chapter.entity_id; no FK because Chapter is SCD2.
    chapter_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    __table_args__ = (
        Index(
            "uq_users_email_current",
            "email",
            unique=True,
            sqlite_where=text("valid_until IS NULL"),
            postgresql_where=text("valid_until IS NULL"),
        ),
    )
