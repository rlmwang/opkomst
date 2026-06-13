"""Event business logic that's shared across routers.

Public slug lookups come in two flavours:

* ``get_public_event_by_slug`` — live-only. The signup POST gates
  on this so an archived event can't accept new sign-ups.
* ``get_event_by_slug_any`` — returns archived rows too. The
  public ``GET /by-slug/{slug}`` uses this so the page can render
  a "this event has been archived" message instead of a generic
  404. Share surfaces (ICS, QR, previews) keep using the
  live-only version — no point handing out a calendar invite
  for an archived event.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..models import Event

# Single source of truth: ``Event.starts_at`` / ``ends_at`` are
# naive timestamps in Europe/Amsterdam wall clock (see the model
# docstring). Comparisons against "now" must be in the same frame
# — never ``datetime.now(UTC)``, that's two hours off and was the
# whole reason reminder emails sent the wrong time.
_AMS = ZoneInfo("Europe/Amsterdam")


def now_wallclock() -> datetime:
    """Naive Europe/Amsterdam wall-clock 'now'. Independent of the
    server / container TZ so dev machines and the production
    container behave the same."""
    return datetime.now(_AMS).replace(tzinfo=None)


def get_public_event_by_slug(db: Session, slug: str) -> Event | None:
    """Live (non-archived) event by slug. Returns None when the
    slug is unknown OR the event has been archived."""
    return db.query(Event).filter(Event.slug == slug, Event.archived_at.is_(None)).first()


def get_event_by_slug_any(db: Session, slug: str) -> Event | None:
    """Any event by slug, archived or not. Public surfaces that
    want to render a soft "this event is archived" message use
    this and check ``archived_at`` themselves."""
    return db.query(Event).filter(Event.slug == slug).first()
