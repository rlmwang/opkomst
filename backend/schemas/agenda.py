from datetime import datetime

from pydantic import BaseModel

from .chapters import ChapterPublicOut


class EventCardOut(BaseModel):
    """One event as it appears on a chapter agenda card. Deliberately
    narrower than ``EventOut``: no coordinates, option lists, or lifecycle
    flags, so the public grid leaks less than the sign-up page."""

    slug: str
    name: str
    topic: str | None
    starts_at: datetime
    ends_at: datetime
    location: str
    image_url: str | None
    image_artist_instagram: str | None
    attendee_count: int


class ChapterAgendaOut(BaseModel):
    """A chapter's public agenda: its identity, the upcoming events, and
    a recent-past section (back to the start of the last full calendar
    month)."""

    chapter: ChapterPublicOut
    upcoming: list[EventCardOut]
    past: list[EventCardOut]
