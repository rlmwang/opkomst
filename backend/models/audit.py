from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class AuditLog(UUIDMixin, TimestampMixin, Base):
    """Records admin-only mutations: approvals, promotions, demotions.

    Read endpoints and signup writes are *not* logged here — that's
    deliberate, see CLAUDE.md "no PII in logs".
    """

    __tablename__ = "audit_log"

    actor_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # approve | promote | demote
    target_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
