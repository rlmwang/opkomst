"""Event business logic that's shared across routers.

Today this is just the public slug lookup (used by three endpoints —
``GET /events/by-slug/{slug}``, ``GET /events/by-slug/{slug}/qr.png``,
``POST /events/by-slug/{slug}/signups``). Adding a new public-by-slug
caller is a one-liner now."""

from sqlalchemy.orm import Session

from ..models import Event
from . import scd2


def get_public_event_by_slug(db: Session, slug: str) -> Event | None:
    """Resolve a public slug to its current, non-archived Event row.
    Returns None when the slug is unknown or the event is archived;
    the caller decides whether that's a 404 or some other shape."""
    return (
        scd2.current(db.query(Event))
        .filter(Event.slug == slug, Event.archived_at.is_(None))
        .first()
    )
