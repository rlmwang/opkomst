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

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, joinedload

from ..models import Occurrence
from ..schemas.events import EventOptionOut, ProjectedOccurrenceOut, PublicEventOut, PublicOccurrenceOut
from . import event_recurrence, tenancy
from . import image as image_svc

# Single source of truth: occurrence / event datetimes are naive
# Europe/Amsterdam wall clock (see the model docstrings). Comparisons
# against "now" must be in the same frame — never ``datetime.now(UTC)``,
# that's two hours off and was the whole reason reminder emails sent the
# wrong time.
_AMS = ZoneInfo("Europe/Amsterdam")


def apply_options(db: Session, event: Any, model: Any, existing: Sequence[Any], payload: Sequence[Any]) -> None:
    """Diff-apply one of an event's option lists, matched by id.

    The same rule as a form question's choices: an option carrying an id
    is the one existing sign-ups point at, so a rename is an update to
    ``label``. One with no id is new; one on disk the payload no longer
    mentions is deleted, and the foreign key decides what that does to
    the sign-ups holding it (``docs/design-question-edits.md``).
    """
    by_id = {o.id: o for o in existing}
    seen: set[str] = set()
    for ordinal, opt in enumerate(payload, start=1):
        if opt.id and opt.id in by_id:
            row = by_id[opt.id]
            row.ordinal = ordinal
            row.label = opt.label.strip()
            seen.add(opt.id)
        else:
            db.add(model(event_id=event.id, ordinal=ordinal, label=opt.label.strip()))
    for oid, row in by_id.items():
        if oid not in seen:
            db.delete(row)


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
    # Filtered from the event's own sessions rather than queried
    # separately. The "sessie i van N" on this page already reads the
    # full list (``session_index`` / ``total_sessions``), so a second
    # query for the subset of it that hasn't ended was fetching rows the
    # request had in hand. The relationship is ordered by ``starts_at``,
    # which is the order this list wants.
    upcoming_rows = [o for o in event.occurrences if o.ends_at > now]
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
        # A switched-off question isn't asked, so its options never
        # reach the page.
        source_options=[EventOptionOut.model_validate(o) for o in event.source_options] if event.source_enabled else [],
        help_options=[EventOptionOut.model_validate(o) for o in event.help_options] if event.help_enabled else [],
        image_url=image_svc.public_url(event.image_path),
        image_artist_instagram=event.image_artist_instagram,
        locale=event.locale,
        archived=event.archived_at is not None,
        reminder_enabled=event.reminder_enabled,
        feedback_enabled=event.feedback_enabled,
        name_required=event.name_required,
        answers_editable=event.answers_editable,
        is_recurring=bool(event.cycle_slots),
        total_sessions=event_recurrence.total_sessions(event),
        current=PublicOccurrenceOut(
            id=current.id,
            slug=current.slug,
            index=event_recurrence.session_index(event, current),
            starts_at=current.starts_at,
            ends_at=current.ends_at,
            is_current=True,
        ),
        upcoming=[
            PublicOccurrenceOut(
                id=o.id,
                slug=o.slug,
                index=event_recurrence.session_index(event, o),
                starts_at=o.starts_at,
                ends_at=o.ends_at,
                is_current=o.id == current.id,
            )
            for o in upcoming_rows
        ],
        # Numbered on from the last materialised session: a projected date
        # is the next session, it just has no row yet.
        projected=[
            ProjectedOccurrenceOut(
                index=event_recurrence.session_count(event) + i, starts_at=s.starts_at, ends_at=s.ends_at
            )
            for i, s in enumerate(projected)
        ],
    )
