from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..mixins import TimestampMixin, UUIDMixin


class Event(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "events"

    # 8-char nanoid, public — appears in /e/{slug} URLs.
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Organiser-defined options for the "How did you find us?" dropdown.
    # JSON array of strings, e.g. ["Flyer", "Word of mouth", "Social media"].
    source_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False, index=True)


class Signup(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "signups"

    event_id: Mapped[str] = mapped_column(Text, ForeignKey("events.id"), nullable=False, index=True)
    # Free-text "name" — attendee can use a pseudonym. Required so the
    # organiser has *something* to recognise on a head-count list.
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Must match one of the parent event's source_options.
    source_choice: Mapped[str] = mapped_column(Text, nullable=False)
    # Encrypted email blob (AES-GCM via services.encryption). Nullable
    # because supplying an email is opt-in. Hard-deleted (set to NULL)
    # after the feedback worker runs — successful or failed-after-retry.
    encrypted_email: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # When the feedback worker processed this row. Set even on send
    # failures (after one retry) so we don't keep the ciphertext around.
    feedback_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
