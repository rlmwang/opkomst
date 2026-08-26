from datetime import datetime

from pydantic import BaseModel

from .chapters import ChapterPublicOut


class OccurrenceCardOut(BaseModel):
    """One occurrence as it appears on a chapter agenda card. Deliberately
    narrower than the sign-up DTO: no coordinates, option lists, or
    lifecycle flags, so the public grid leaks less than the sign-up page.
    ``index`` + ``total_sessions`` drive the "sessie i van N" badge
    (``total_sessions`` null = open-ended series)."""

    slug: str  # the occurrence's public slug (/e/{slug})
    name_nl: str | None
    name_en: str | None
    topic_nl: str | None
    topic_en: str | None
    starts_at: datetime
    ends_at: datetime
    location: str | None
    image_url: str | None
    image_artist_instagram: str | None
    attendee_count: int
    index: int
    total_sessions: int | None


class ChapterAgendaOut(BaseModel):
    """A chapter's public agenda: its identity, the upcoming occurrences
    (within a rolling one-month display window), and a recent-past section
    (back to the start of the last full calendar month)."""

    chapter: ChapterPublicOut
    upcoming: list[OccurrenceCardOut]
    past: list[OccurrenceCardOut]
