from sqlalchemy import Boolean, Text
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
    # Admin must approve every new account. Unapproved users can log in
    # (so they see the "awaiting approval" message) but cannot create events.
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
