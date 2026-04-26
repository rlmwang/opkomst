from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Afdeling(UUIDMixin, TimestampMixin, Base):
    """A local chapter / department.

    SCD2-versioned: every change creates a new row, the current
    version is the row with ``valid_until IS NULL``. Soft-delete is
    just ``valid_until = now`` with no replacement row; restore
    inserts a new row with ``valid_until = NULL`` and the same
    ``entity_id``.

    External references (Event.afdeling_id, User.afdeling_id) point
    at ``entity_id`` so they survive edits and restores.
    """

    __tablename__ = "afdelingen"

    name: Mapped[str] = mapped_column(Text, nullable=False)

    # SCD2 columns. entity_id is the stable logical id — first version
    # of an afdeling self-references (entity_id = id).
    entity_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    changed_by: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    # "created" | "updated" | "archived" | "restored"
    change_kind: Mapped[str] = mapped_column(Text, nullable=False)
