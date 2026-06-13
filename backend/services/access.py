"""Access-checked entity lookups for the routers.

Multi-chapter membership lives in ``user_chapters``. A user
sees a chapter-scoped entity (event, form) iff its ``chapter_id``
is in their *live* chapter set (membership rows pointing at
soft-deleted chapters are filtered out at read time, same as
everywhere else in the app). Admins see everything; the chapter
filter is purely an organiser-side scope.

The existence of an entity in a chapter the user can't see is
never disclosed via the difference between 404 and 403 — it's
always 404.

The chapter-scope rule is one implementation (``get_scoped`` /
``scope_filter`` / ``list_filter``), parametrised by the model.
Events and forms get one-line wrappers so the security guarantee
lives in exactly one place. Archived-entity handling stays in the
routers because the right status varies (409 for "archive an
already-archived entity", 200 for /restore, 404/410 for the
public by-slug routes).
"""

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import false
from sqlalchemy.orm import Mapped, Session
from sqlalchemy.sql import ColumnElement

from ..models import Chapter, Datepoll, Event, Form, User, UserChapter

# ``Event`` / ``Form`` / ``Datepoll`` each carry an ``id`` and a
# chapter-scoping ``chapter_id`` — the only two columns the scope
# rule touches.
_Scoped = TypeVar("_Scoped", Event, Form, Datepoll)


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


def scope_filter(db: Session, user: User, column: "Mapped[str | None]") -> ColumnElement[bool]:
    """SQL predicate scoping a list query to the user's chapter set.
    A user with zero live memberships sees an empty list (the
    predicate evaluates to ``FALSE``); admins match every row
    because every chapter id is in their effective set."""
    ids = chapter_ids_for_user(db, user)
    if not ids:
        return false()
    return column.in_(ids)


def list_filter(
    db: Session,
    user: User,
    column: "Mapped[str | None]",
    chapter_id: str | None,
) -> ColumnElement[bool]:
    """WHERE clause for an organiser list query. ``chapter_id`` is
    the optional UI filter; without it we return every row in the
    user's full chapter set. With it, the chosen chapter still has
    to be one the caller belongs to."""
    if chapter_id is None:
        return scope_filter(db, user, column)
    assert_user_can_assign_chapter(db, user, chapter_id)
    return column == chapter_id


def get_scoped(
    db: Session,
    model: type[_Scoped],
    entity_id: str,
    user: User,
    *,
    not_found: str,
) -> _Scoped:
    """Fetch a chapter-scoped entity by id, scoped to the user's
    chapter set. 404 if missing, in a chapter the user can't see,
    or the user has no live memberships."""
    ids = chapter_ids_for_user(db, user)
    if not ids:
        raise HTTPException(status_code=404, detail=not_found)
    row = db.query(model).filter(model.id == entity_id, model.chapter_id.in_(ids)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=not_found)
    return row


def assert_user_can_assign_chapter(db: Session, user: User, chapter_id: str) -> None:
    """Used by create/update to gate the user-supplied ``chapter_id``
    against the caller's own membership set. 403 rather than 404
    because the caller deliberately picked this chapter — they know
    it exists, so we can be honest about why we're rejecting it."""
    if chapter_id not in chapter_ids_for_user(db, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to that chapter",
        )


# --- Per-entity wrappers ---------------------------------------------
# One-liners over the generic helpers so call sites read naturally
# and the scope rule stays single-sourced above.


def event_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Event.chapter_id)


def get_event_for_user(db: Session, event_id: str, user: User) -> Event:
    return get_scoped(db, Event, event_id, user, not_found="Event not found")


def form_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Form.chapter_id)


def get_form_for_user(db: Session, form_id: str, user: User) -> Form:
    return get_scoped(db, Form, form_id, user, not_found="Form not found")


def datepoll_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Datepoll.chapter_id)


def get_datepoll_for_user(db: Session, datepoll_id: str, user: User) -> Datepoll:
    return get_scoped(db, Datepoll, datepoll_id, user, not_found="Datepoll not found")
