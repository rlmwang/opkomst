"""Access-checked entity lookups for the routers.

The pattern of "scd2-current + chapter scope" used to be inlined
in every event-touching route, with the ``"__no_match__"`` magic
string as the workaround for users without a chapter (the audit
flagged that smell). One helper, applied uniformly:

* SCD2-current row only (history is invisible to the API).
* Chapter scope: a user with ``chapter_id=None`` sees nothing;
  the existence of an event in another chapter doesn't leak via
  the difference between 404 and 403 — it's always 404.

Archived-event handling stays in the routers because the right
status varies (409 for "archive an already-archived event", 410
for the public by-slug route, 200 for /restore). A helper that
forced one answer would have to either be three helpers or take
flags that flatten the meaningful difference.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Event, User
from . import scd2 as scd2_svc


def get_event_for_user(db: Session, entity_id: str, user: User) -> Event:
    """Fetch the current version of an event by entity_id, scoped
    to the user's chapter. 404 if missing, in another chapter, or
    the user has no chapter."""
    if user.chapter_id is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = (
        scd2_svc.current(db.query(Event))
        .filter(
            Event.entity_id == entity_id,
            Event.chapter_id == user.chapter_id,
        )
        .first()
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
