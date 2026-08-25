"""Public chapter-agenda read model.

``build_agenda`` turns a chapter into its ``ChapterAgendaOut``: the
upcoming **occurrences** (materialised, not yet ended, within a rolling
one-month display window) and a recent-past section going back to the
start of the last full calendar month. Both filter on the event's
``listed IS TRUE`` and ``archived_at IS NULL``. A bi-weekly course
therefore shows at most a couple of cards at a time. Times are naive
Europe/Amsterdam wall-clock, matching how occurrences are stored.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from ..models import Chapter, Event, Occurrence
from ..schemas.agenda import ChapterAgendaOut, OccurrenceCardOut
from ..schemas.chapters import ChapterPublicOut
from . import event_recurrence, event_stats
from . import image as image_svc
from .events import now_wallclock

# How far ahead the agenda shows occurrences. Separate from (and shorter
# than) the materialisation horizon — the display window bounds the grid
# so a weekly series doesn't flood the page.
DISPLAY_HORIZON = timedelta(days=31)


def _last_full_month_start(now: datetime) -> datetime:
    """First day (00:00) of the previous calendar month. The current
    month isn't 'full' yet, so the past window's floor is last month's
    first day; on 2026-07-08 that's 2026-06-01."""
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return last_of_prev_month.replace(day=1)


def _card(occ: Occurrence, totals: dict[str, int]) -> OccurrenceCardOut:
    event = occ.event
    return OccurrenceCardOut(
        slug=occ.slug,
        name_nl=event.name_nl,
        name_en=event.name_en,
        topic_nl=event.topic_nl,
        topic_en=event.topic_en,
        starts_at=occ.starts_at,
        ends_at=occ.ends_at,
        location=event.location,
        image_url=image_svc.public_url(event.image_path),
        image_artist_instagram=event.image_artist_instagram,
        attendee_count=totals.get(occ.id, 0),
        index=event_recurrence.session_index(event, occ.starts_at.date()),
        total_sessions=event_recurrence.total_sessions(event),
    )


def build_agenda(db: Session, chapter: Chapter) -> ChapterAgendaOut:
    now = now_wallclock()
    cutoff = _last_full_month_start(now)

    base = (
        db.query(Occurrence)
        .options(joinedload(Occurrence.event))
        .join(Event, Event.id == Occurrence.event_id)
        .filter(
            # The tenant, not only the chapter. ``chapter_id`` is a bare
            # FK: a row in another tenant that carries this chapter's id
            # would otherwise be published on this organisation's public
            # agenda. The write paths refuse to create one; the read
            # refuses to show one.
            Event.tenant_id == chapter.tenant_id,
            Event.chapter_id == chapter.id,
            Event.archived_at.is_(None),
            Event.listed.is_(True),
        )
    )
    upcoming = (
        base.filter(Occurrence.ends_at >= now, Occurrence.starts_at <= now + DISPLAY_HORIZON)
        .order_by(Occurrence.starts_at.asc())
        .all()
    )
    past = (
        base.filter(Occurrence.ends_at < now, Occurrence.starts_at >= cutoff)
        .order_by(Occurrence.starts_at.desc())
        .all()
    )

    totals = event_stats.occurrence_totals(db, [o.id for o in (*upcoming, *past)])
    return ChapterAgendaOut(
        chapter=ChapterPublicOut(name=chapter.name, slug=chapter.slug, city=chapter.city),
        upcoming=[_card(o, totals) for o in upcoming],
        past=[_card(o, totals) for o in past],
    )
