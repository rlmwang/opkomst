"""Public chapter-agenda read model.

``build_agenda`` turns a chapter into its ``ChapterAgendaOut``: the
upcoming events (not yet ended) and a recent-past section going back to
the start of the last full calendar month. Both filter on
``listed IS TRUE`` and ``archived_at IS NULL``. Times are naive
Europe/Amsterdam wall-clock, matching how events are stored.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Chapter, Event
from ..schemas.agenda import ChapterAgendaOut, EventCardOut
from ..schemas.chapters import ChapterPublicOut
from . import event_stats
from .events import now_wallclock


def _last_full_month_start(now: datetime) -> datetime:
    """First day (00:00) of the previous calendar month. The current
    month isn't 'full' yet, so the past window's floor is last month's
    first day; on 2026-07-08 that's 2026-06-01."""
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return last_of_prev_month.replace(day=1)


def _card(event: Event, totals: dict[str, int]) -> EventCardOut:
    return EventCardOut(
        slug=event.slug,
        name=event.name,
        topic=event.topic,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        location=event.location,
        image_url=event.image_url,
        image_artist_instagram=event.image_artist_instagram,
        attendee_count=totals.get(event.id, 0),
    )


def build_agenda(db: Session, chapter: Chapter) -> ChapterAgendaOut:
    now = now_wallclock()
    cutoff = _last_full_month_start(now)

    base = db.query(Event).filter(
        Event.chapter_id == chapter.id,
        Event.archived_at.is_(None),
        Event.listed.is_(True),
    )
    upcoming = base.filter(Event.ends_at >= now).order_by(Event.starts_at.asc()).all()
    past = base.filter(Event.ends_at < now, Event.starts_at >= cutoff).order_by(Event.starts_at.desc()).all()

    totals = event_stats.attendee_totals(db, [e.id for e in (*upcoming, *past)])
    return ChapterAgendaOut(
        chapter=ChapterPublicOut(name=chapter.name, slug=chapter.slug, city=chapter.city),
        upcoming=[_card(e, totals) for e in upcoming],
        past=[_card(e, totals) for e in past],
    )
