"""Public chapter-agenda read model.

``build_agenda`` turns a chapter into its ``ChapterAgendaOut``: the
upcoming **occurrences** (materialised, not yet ended) and a
recent-past section, both inside a rolling window the owning tenant
sets — ``agenda_future_days`` forward and ``agenda_past_days`` back,
edited at ``/settings`` (``routers/tenant_settings.py``). Both filter
on the event's ``listed IS TRUE`` and ``archived_at IS NULL``. Times
are naive Europe/Amsterdam wall-clock, matching how occurrences are
stored.

The window is deliberately not the materialisation horizon: events
are materialised further out than they are shown, so widening the
window here surfaces occurrences that already exist.
"""

from datetime import timedelta

from sqlalchemy.orm import Session, joinedload

from ..models import Chapter, Event, Occurrence
from ..schemas.agenda import ChapterAgendaOut, OccurrenceCardOut
from ..schemas.chapters import ChapterPublicOut
from . import event_recurrence, event_stats
from . import image as image_svc
from .events import now_wallclock


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
    # The chapter's own tenant, never the bound one: this is a public
    # read and the URL is what resolved the chapter, so the window has
    # to come from the row the page is actually about.
    tenant = chapter.tenant
    horizon = now + timedelta(days=tenant.agenda_future_days)
    cutoff = now - timedelta(days=tenant.agenda_past_days)

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
        base.filter(Occurrence.ends_at >= now, Occurrence.starts_at <= horizon)
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
