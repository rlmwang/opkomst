from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Chapter(UUIDMixin, TimestampMixin, Base):
    """A local chapter / department.

    Soft-delete via ``deleted_at``. Restore is "clear
    ``deleted_at``" — the same row id survives, so anything that
    referenced the chapter (users, events) keeps pointing at the
    right thing automatically. Edit history isn't tracked here;
    a chapter rename overwrites the name in place."""

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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        # Chapter names are unique across live chapters
        # (case-insensitive lookup is the dupe check; the index is
        # plain to keep it simple — the dupe check in
        # ``services.chapters.name_exists_active`` is the real gate).
        Index(
            "uq_chapters_name_live",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
