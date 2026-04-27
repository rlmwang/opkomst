from sqlalchemy import Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import SCD2Mixin, TimestampMixin, UUIDMixin


class Chapter(UUIDMixin, TimestampMixin, SCD2Mixin, Base):
    """A local chapter / department. SCD2 dimension — see
    ``mixins.SCD2Mixin`` for chain semantics. External references
    (``Event.chapter_id``, ``User.chapter_id``) point at
    ``entity_id`` so they survive every edit / archive / restore."""

    __tablename__ = "chapters"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional anchor city — used to bias address autocomplete on
    # event creation toward streets near this chapter's home town.
    # Stored as display name (``city``) plus the centroid coords
    # (``city_lat`` / ``city_lon``) so the LocationPicker doesn't
    # need a roundtrip to PDOK to resolve the city on every event.
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    city_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    city_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
