"""Event business logic shared across routers.

The public sign-up page is per **occurrence** (``Occurrence.slug``), so
public lookups resolve a slug to an occurrence and read the event content
through it. Two flavours, mirroring the old event lookups:

* ``get_public_occurrence_by_slug`` — live-only (event not archived). The
  signup POST gates on this so an archived event can't accept sign-ups.
* ``get_occurrence_by_slug_any`` — returns occurrences of archived events
  too, so the public page can render a soft "this event has been
  archived" message instead of a generic 404.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from ..models import Occurrence
from ..schemas.events import ProjectedOccurrenceOut, PublicEventOut, PublicOccurrenceOut
from . import event_recurrence, tenancy
from . import image as image_svc

# Single source of truth: occurrence / event datetimes are naive
# Europe/Amsterdam wall clock (see the model docstrings). Comparisons
# against "now" must be in the same frame — never ``datetime.now(UTC)``,
# that's two hours off and was the whole reason reminder emails sent the
# wrong time.
_AMS = ZoneInfo("Europe/Amsterdam")


def now_wallclock() -> datetime:
    """Naive Europe/Amsterdam wall-clock 'now'. Independent of the
    server / container TZ so dev machines and the production container
    behave the same."""
    return datetime.now(_AMS).replace(tzinfo=None)


def get_occurrence_by_slug_any(db: Session, slug: str) -> Occurrence | None:
    """Any occurrence by slug, its event archived or not, with the event
    eager-loaded. Public surfaces that want to render a soft "this event
    is archived" message use this and check ``event.archived_at``.

    Binds the owning tenant: the public URL carries none, so the
    occurrence behind the slug is what decides whose organisation this
    request is in (branding included)."""
    occ = db.query(Occurrence).options(joinedload(Occurrence.event)).filter(Occurrence.slug == slug).first()
    if occ is not None:
        tenancy.bind(occ.tenant_id, occ.tenant.brand_slug)
    return occ


def get_public_occurrence_by_slug(db: Session, slug: str) -> Occurrence | None:
    """Live occurrence by slug (event not archived), event eager-loaded.
    Returns None when the slug is unknown OR the event is archived."""
    occ = get_occurrence_by_slug_any(db, slug)
    if occ is None or occ.event.archived_at is not None:
        return None
    return occ


def build_public_event(db: Session, current: Occurrence) -> PublicEventOut:
    """The public per-occurrence sign-up DTO: the event content read
    through the parent, the landing occurrence, the other upcoming
    occurrences the visitor can also book (materialised, not yet ended),
    and the projected beyond-horizon dates shown as not-yet-open."""
    event = current.event
    now = now_wallclock()
    upcoming_rows = (
        db.query(Occurrence)
        .filter(Occurrence.event_id == event.id, Occurrence.ends_at > now)
        .order_by(Occurrence.starts_at.asc())
        .all()
    )
    projected = event_recurrence.projected_future_specs(event, now)
    return PublicEventOut(
        event_slug=event.slug,
        name_nl=event.name_nl,
        name_en=event.name_en,
        topic_nl=event.topic_nl,
        topic_en=event.topic_en,
        location=event.location,
        latitude=event.latitude,
        longitude=event.longitude,
        source_options=event.source_options,
        help_options=event.help_options,
        image_url=image_svc.public_url(event.image_path),
        image_artist_instagram=event.image_artist_instagram,
        locale=event.locale,
        archived=event.archived_at is not None,
        is_recurring=bool(event.cycle_slots),
        total_sessions=event_recurrence.total_sessions(event),
        current=PublicOccurrenceOut(
            id=current.id,
            slug=current.slug,
            index=event_recurrence.session_index(event, current.starts_at.date()),
            starts_at=current.starts_at,
            ends_at=current.ends_at,
            is_current=True,
        ),
        upcoming=[
            PublicOccurrenceOut(
                id=o.id,
                slug=o.slug,
                index=event_recurrence.session_index(event, o.starts_at.date()),
                starts_at=o.starts_at,
                ends_at=o.ends_at,
                is_current=o.id == current.id,
            )
            for o in upcoming_rows
        ],
        projected=[ProjectedOccurrenceOut(index=s.index, starts_at=s.starts_at, ends_at=s.ends_at) for s in projected],
    )
