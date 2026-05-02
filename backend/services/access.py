"""Access-checked entity lookups for the routers.

Multi-chapter membership lives in ``user_chapters``. A user
sees an event iff its ``chapter_id`` is in their *live* chapter
set (membership rows pointing at soft-deleted chapters are
filtered out at read time, same as everywhere else in the app).
Admins see every event; the chapter filter is purely an
organiser-side scope.

The existence of an event in a chapter the user can't see is
never disclosed via the difference between 404 and 403 — it's
always 404.

Archived-event handling stays in the routers because the right
status varies (409 for "archive an already-archived event", 200
for /restore, 404 for the public by-slug route).
"""

from fastapi import HTTPException
from sqlalchemy import false
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from ..models import Chapter, Event, User, UserChapter


def chapter_ids_for_user(db: Session, user: User) -> set[str]:
    """Live chapter ids the user belongs to. Admins are global —
    they implicitly belong to every live chapter, including ones
    they were never explicitly assigned to. Live filter on
    ``Chapter.deleted_at IS NULL`` so soft-deleted chapters drop
    out without an admin having to re-assign people."""
    if user.role == "admin":
        rows = db.query(Chapter.id).filter(Chapter.deleted_at.is_(None)).all()
        return {row[0] for row in rows}
    rows = (
        db.query(UserChapter.chapter_id)
        .join(Chapter, Chapter.id == UserChapter.chapter_id)
        .filter(UserChapter.user_id == user.id, Chapter.deleted_at.is_(None))
        .all()
    )
    return {row[0] for row in rows}


def event_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    """SQL predicate scoping an event-list query to the user's
    chapter set. A user with zero live memberships sees an empty
    list (the predicate evaluates to ``FALSE``); admins see
    everything (the predicate is ``TRUE`` because every
    ``Event.chapter_id`` is in their effective set, but we keep
    the check explicit for parity)."""
    ids = chapter_ids_for_user(db, user)
    if not ids:
        return false()
    return Event.chapter_id.in_(ids)


def get_event_for_user(db: Session, event_id: str, user: User) -> Event:
    """Fetch an event by id, scoped to the user's chapter set.
    404 if missing, in a chapter the user can't see, or the user
    has no live memberships."""
    ids = chapter_ids_for_user(db, user)
    if not ids:
        raise HTTPException(status_code=404, detail="Event not found")
    event = db.query(Event).filter(Event.id == event_id, Event.chapter_id.in_(ids)).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def assert_user_can_assign_chapter(db: Session, user: User, chapter_id: str) -> None:
    """Used by event create/update to gate the user-supplied
    ``chapter_id`` against the caller's own membership set. 403
    rather than 404 because the caller deliberately picked this
    chapter — they know it exists, so we can be honest about why
    we're rejecting it."""
    if chapter_id not in chapter_ids_for_user(db, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to that chapter",
        )
