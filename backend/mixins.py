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
        return mapped_column(DateTime(timezone=True),nullable=False, default=_now)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True),nullable=False, default=_now, onupdate=_now)


class SCD2Mixin:
    """Strict SCD2 dimension columns. A logical entity is a chain of
    rows sharing one ``entity_id``. The current row has
    ``valid_until IS NULL``; every other row in the chain is history.
    The row id changes on every edit, but ``entity_id`` is stable
    across the chain — it's the only id that ever leaves the backend
    (DTOs expose ``entity_id`` as ``id``).

    External references between SCD2 tables point at ``entity_id``
    (not row id), so they survive every edit / archive / restore.
    There's no FK constraint on those columns — ``entity_id`` is not
    unique across all rows (history rows share it). Integrity is
    enforced by routing every read through ``services.scd2.current``."""

    @declared_attr
    def entity_id(cls) -> Mapped[str]:
        return mapped_column(Text, nullable=False, index=True)

    @declared_attr
    def valid_from(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True),nullable=False, default=_now)

    @declared_attr
    def valid_until(cls) -> Mapped[datetime | None]:
        return mapped_column(DateTime(timezone=True),nullable=True, index=True)

    @declared_attr
    def changed_by(cls) -> Mapped[str]:
        # Points at User.entity_id. No FK — see SCD2Mixin docstring.
        return mapped_column(Text, nullable=False)

    @declared_attr
    def change_kind(cls) -> Mapped[str]:
        # "created" | "updated" | "archived" | "restored"
        return mapped_column(Text, nullable=False)
