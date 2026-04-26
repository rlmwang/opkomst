from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, Text
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
    # Optional coordinates from Nominatim. Both null = free-text location only;
    # both set = render a Leaflet pin on the public page.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Organiser-defined options for the "How did you find us?" dropdown.
    # JSON array of strings, e.g. ["Flyer", "Word of mouth", "Social media"].
    source_options: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # When false, the public signup form omits the email field and the
    # post-event feedback mail is never sent for this event. Default on
    # so feedback collection is the path of least resistance.
    questionnaire_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False, index=True)
    # The afdeling that owns this event. Points at Afdeling.entity_id
    # (not row id) so the link survives edits / restores. Nullable in
    # the schema only because pre-feature events predate the column;
    # every newly-created event must have one.
    afdeling_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    # Soft-archive: organisers can hide events from the dashboard +
    # public page without deleting any signups / feedback. Restore
    # flips this back to NULL.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


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
    # Per-signup feedback-email lifecycle. Values:
    #   not_applicable  — no email was supplied (or questionnaire was off)
    #   pending         — email supplied, worker hasn't processed yet
    #   sent            — worker handed the message off to SMTP successfully
    #   bounced         — provider reported a hard bounce via webhook
    #   failed          — worker couldn't decrypt or SMTP threw after retry
    feedback_email_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_applicable", index=True
    )
    # When the feedback worker processed this row. Set even on send
    # failures (after one retry) so we don't keep the ciphertext around.
    feedback_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Provider message id (Scaleway TEM returns one on send). Stored so
    # we can correlate webhook bounce events back to the specific signup.
    # Null when send failed, when no provider returned an id, or before send.
    feedback_message_id: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
