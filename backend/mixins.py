from datetime import UTC, datetime

from sqlalchemy import DateTime, Text
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


class TimestampMixin:
    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), nullable=False, default=_now)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
