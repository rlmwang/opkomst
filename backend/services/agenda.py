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

**Read with Core, not the ORM.** This is the most-visited page in the
app and it builds cards, not entities: nothing here is edited, so the
identity map, the attribute instrumentation and the lazy loaders are
all cost with no use. Selecting the columns the card needs and handing
them straight to Pydantic cut the handler's SQLAlchemy time roughly in
half, and dropped the page from five queries to three. The writes stay
on the ORM, where the tenant write guard lives
(``services/tenancy.install_write_guard``).
"""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Subquery

from ..models import Chapter, Event, Occurrence, Tenant
from ..schemas.agenda import ChapterAgendaOut, OccurrenceCardOut
from ..schemas.chapters import ChapterPublicOut
from . import event_stats
from . import image as image_svc
from .events import now_wallclock


def _listed_occurrences(chapter: Chapter) -> Subquery:
    """Every listed occurrence of the chapter, with its rank among its
    own event's sessions.

    The card says "sessie 2 van 5", which is the row's position among
    *all* its event's occurrences, not among the ones this page happens
    to show. So the ranking is computed here, before any date filter,
    and the window is applied to the result. Doing it the other way
    round numbers the sessions relative to today, which changes what a
    card says as time passes.

    ``total_sessions`` is left to the caller: an open-ended recurring
    event has no total, and that is a fact about the event's rule rather
    than about how many rows exist today.
    """
    ranked = (
        select(
            Occurrence.id,
            Occurrence.slug,
            Occurrence.starts_at,
            Occurrence.ends_at,
            Event.name_nl,
            Event.name_en,
            Event.topic_nl,
            Event.topic_en,
            Event.location,
            Event.image_path,
            Event.image_artist_instagram,
            Event.cycle_slots,
            Event.span_weeks,
            (func.row_number().over(partition_by=Occurrence.event_id, order_by=Occurrence.starts_at) - 1).label(
                "session_index"
            ),
            func.count().over(partition_by=Occurrence.event_id).label("session_count"),
        )
        .join(Event, Event.id == Occurrence.event_id)
        .where(
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
    return ranked.subquery()


def _card(row, totals: dict[str, int]) -> OccurrenceCardOut:
    return OccurrenceCardOut(
        slug=row.slug,
        name_nl=row.name_nl,
        name_en=row.name_en,
        topic_nl=row.topic_nl,
        topic_en=row.topic_en,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        location=row.location,
        image_url=image_svc.card_url(row.image_path),
        image_artist_instagram=row.image_artist_instagram,
        attendee_count=totals.get(row.id, 0),
        index=row.session_index,
        # An open-ended recurring event's list never closes, so it has no
        # "van N" (``event_recurrence.total_sessions``, same rule).
        total_sessions=None if (row.cycle_slots and row.span_weeks is None) else row.session_count,
    )


def build_agenda(db: Session, chapter: Chapter, tenant: Tenant) -> ChapterAgendaOut:
    """The chapter's page. ``tenant`` is the organisation that owns it,
    passed in rather than read off ``chapter.tenant``: both callers
    resolved it from the first path segment to get here, and reaching
    through the relationship made the page fetch the same row a second
    time.

    It is the chapter's own tenant and never the bound one. This is a
    public read, the URL is what resolved the chapter, and the window
    has to come from the row the page is actually about."""
    now = now_wallclock()
    horizon = now + timedelta(days=tenant.agenda_future_days)
    cutoff = now - timedelta(days=tenant.agenda_past_days)

    occ = _listed_occurrences(chapter)
    # Both halves of the page in one trip: the split is a property of
    # each row against ``now``, not two different questions.
    rows = db.execute(
        select(*occ.c).where(
            ((occ.c.ends_at >= now) & (occ.c.starts_at <= horizon))
            | ((occ.c.ends_at < now) & (occ.c.starts_at >= cutoff))
        )
    ).all()

    upcoming = sorted((r for r in rows if r.ends_at >= now), key=lambda r: r.starts_at)
    past = sorted((r for r in rows if r.ends_at < now), key=lambda r: r.starts_at, reverse=True)
    totals = event_stats.occurrence_totals(db, [r.id for r in rows])
    return ChapterAgendaOut(
        chapter=ChapterPublicOut(name=chapter.name, slug=chapter.slug, city=chapter.city),
        upcoming=[_card(r, totals) for r in upcoming],
        past=[_card(r, totals) for r in past],
    )
