from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Two roles: "organiser" (default on register) and "admin" (granted by another admin).
    role: Mapped[str] = mapped_column(Text, nullable=False, default="organiser")
    # Two gates before an account can act: email verification (the user
    # confirmed they own the address by clicking the link) AND admin
    # approval (someone we trust said this person belongs here). Both
    # must hold; require_approved enforces the conjunction.
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
