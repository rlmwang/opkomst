from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class AuditLog(UUIDMixin, TimestampMixin, Base):
    """Records admin-only mutations: approvals, promotions, demotions.
    ``actor_id`` and ``target_id`` are ``User.entity_id`` values — no
    FK because User is SCD2 (entity_id isn't unique across rows)."""

    __tablename__ = "audit_log"

    actor_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
