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

from typing import Any, TypeVar

from fastapi import HTTPException
from sqlalchemy import and_, false, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from ..models import ArchiveIndex, Chapter, Datepoll, Event, Form, Roster, Tenant, User, UserChapter
from ..models.archive import archive_metadata

# ``Event`` / ``Form`` / ``Datepoll`` / ``Roster`` each carry an ``id``
# and a chapter-scoping ``chapter_id`` — the only two columns the scope
# rule touches.
_Scoped = TypeVar("_Scoped", Event, Form, Datepoll, Roster)


def is_personal(db: Session, user: User) -> bool:
    """Whether the user's account holds a single person and no chapters.

    The rule itself is ``Tenant.is_personal``; this only resolves the
    row to ask. Through ``db`` from ``user.tenant_id`` rather than the
    ``user.tenant`` relationship, because every function in this module
    already takes the session it should read on and the user handed to
    it is not always attached to that session. The row is in the
    identity map for the rest of the request after the first call."""
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:  # pragma: no cover - FK makes this unreachable
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return tenant.is_personal


def chapter_ids_for_user(db: Session, user: User) -> set[str]:
    """Live chapter ids the user belongs to, always within the user's
    own tenant. An admin is global *inside their organisation* — they
    implicitly belong to every live chapter of it, including ones they
    were never explicitly assigned to, and to none of anyone else's.
    Live filter on ``Chapter.deleted_at IS NULL`` so soft-deleted
    chapters drop out without an admin having to re-assign people."""
    if user.role == "admin":
        rows = db.query(Chapter.id).filter(Chapter.tenant_id == user.tenant_id, Chapter.deleted_at.is_(None)).all()
        return {row[0] for row in rows}
    rows = (
        db.query(UserChapter.chapter_id)
        .join(Chapter, Chapter.id == UserChapter.chapter_id)
        .filter(
            UserChapter.user_id == user.id,
            Chapter.tenant_id == user.tenant_id,
            Chapter.deleted_at.is_(None),
        )
        .all()
    )
    return {row[0] for row in rows}


def scope_filter(db: Session, user: User, model: type[_Scoped]) -> ColumnElement[bool]:
    """SQL predicate scoping a query to what this user may see.

    **The tenant is always in it.** For an organisation the chapter set
    narrows it further: a user with zero live memberships sees an empty
    list, and an admin matches every row of their own organisation
    because every one of its chapter ids is in their effective set.

    A personal tenant has no chapters at all and everything in it has
    ``chapter_id IS NULL``, so there the tenant predicate is the whole
    scope — which is why the tenant predicate lives *here*, in the
    filter itself, rather than being left to each caller to remember."""
    same_tenant = model.tenant_id == user.tenant_id
    if is_personal(db, user):
        return same_tenant
    ids = chapter_ids_for_user(db, user)
    if not ids:
        return false()
    return and_(same_tenant, model.chapter_id.in_(ids))


def list_filter(
    db: Session,
    user: User,
    model: type[_Scoped],
    chapter_id: str | None,
) -> ColumnElement[bool]:
    """WHERE clause for an organiser list query. ``chapter_id`` is
    the optional UI filter; without it we return every row the user may
    see. With it, the chosen chapter still has to be one the caller
    belongs to — which a personal tenant never is, since it has none."""
    if chapter_id is None:
        return scope_filter(db, user, model)
    assert_user_can_assign_chapter(db, user, chapter_id)
    return and_(model.tenant_id == user.tenant_id, model.chapter_id == chapter_id)


def get_scoped(
    db: Session,
    model: type[_Scoped],
    entity_id: str,
    user: User,
    *,
    not_found: str,
    where: ColumnElement[bool] | None = None,
) -> _Scoped:
    """Fetch an entity by id, scoped to the user's tenant and — for an
    organisation — their chapter set. 404 if missing, in another tenant,
    in a chapter the user can't see, or the user has no live
    memberships. A personal tenant has no chapters, so there the tenant
    predicate is the whole scope."""
    predicates = [model.id == entity_id, scope_filter(db, user, model)]
    if where is not None:
        # The forms table holds two products; a survey id looked up as
        # a quiz is a 404 rather than a page (docs/design-quizzes.md).
        predicates.append(where)
    row = db.query(model).filter(*predicates).first()
    if row is None:
        raise HTTPException(status_code=404, detail=not_found)
    return row


def scoped_select(
    db: Session,
    model: type[_Scoped],
    user: User,
    *columns: Any,
    chapter_id: str | None = None,
) -> Any:
    """A Core ``SELECT`` of ``columns``, scoped the way ``list_filter``
    scopes an ORM list.

    The read counterpart of ``get_scoped``. A GET endpoint builds a DTO
    and never writes what it read, so it selects the columns its
    response needs instead of hydrating entities the request will throw
    away. The scope rule is the same object in both, so a Core read
    cannot drift from the ORM one it replaced.

    Writes keep using ``get_scoped``: you cannot flush a row that the
    session is not tracking, and the tenant write guard
    (``services/tenancy.install_write_guard``) reads the session's
    identity map to decide whether a write is allowed."""
    return select(*columns).where(list_filter(db, user, model, chapter_id))


def get_scoped_row(
    db: Session,
    model: type[_Scoped],
    entity_id: str,
    user: User,
    *columns: Any,
    not_found: str,
    where: ColumnElement[bool] | None = None,
) -> Any:
    """One row's ``columns``, under exactly the scope ``get_scoped``
    applies, and the same 404 when there is nothing to show."""
    predicates = [model.id == entity_id, scope_filter(db, user, model)]
    if where is not None:
        predicates.append(where)
    row = db.execute(select(*columns).where(*predicates)).first()
    if row is None:
        raise HTTPException(status_code=404, detail=not_found)
    return row


def archived_row(db: Session, root: str, entity_id: str, user: User) -> Any:
    """One archived item's own row, scoped to what this user may see.

    The same rule ``scope_filter`` applies to live rows — the tenant
    always, plus the chapter set for an organisation — asked of the
    archive twin, because an archived item is not in the table
    ``get_scoped`` reads. 404 for missing, another tenant's, or a
    chapter this user has no membership in, so an archived id tells a
    stranger no more than a live one does.
    """
    twin = archive_metadata.tables[f"{root}_archive"]
    predicates = [twin.c.id == entity_id, twin.c.tenant_id == user.tenant_id]
    if not is_personal(db, user):
        ids = chapter_ids_for_user(db, user)
        if not ids:
            raise HTTPException(status_code=404, detail="Not found")
        predicates.append(twin.c.chapter_id.in_(ids))
    row = db.execute(select(twin).where(*predicates)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def archived_rows(
    db: Session,
    root: str,
    user: User,
    chapter_id: str | None = None,
    *,
    mode: str | None = None,
) -> list[Any]:
    """Every archived item of one kind this user may see, newest first.

    Ordered by ``archive_index.archived_at``: the twin holds the item,
    the index holds when it left. Joined rather than denormalised so the
    twin stays an exact mirror of its live table."""
    twin = archive_metadata.tables[f"{root}_archive"]
    predicates = [twin.c.tenant_id == user.tenant_id]
    if mode is not None:
        # The forms table holds surveys, quizzes and kompassen; each
        # router lists only its own, archived or not.
        predicates.append(twin.c.mode == mode)
    if chapter_id is not None:
        assert_user_can_assign_chapter(db, user, chapter_id)
        predicates.append(twin.c.chapter_id == chapter_id)
    elif not is_personal(db, user):
        ids = chapter_ids_for_user(db, user)
        if not ids:
            return []
        predicates.append(twin.c.chapter_id.in_(ids))
    index = ArchiveIndex.__table__
    stmt = (
        select(twin)
        .join(index, (index.c.entity_id == twin.c.id) & (index.c.root == root))
        .where(*predicates)
        .order_by(index.c.archived_at.desc())
    )
    return [row for row in db.execute(stmt).mappings()]


def assert_user_can_assign_chapter(db: Session, user: User, chapter_id: str | None) -> None:
    """Used by create/update to gate the user-supplied ``chapter_id``
    against the caller's own membership set. 403 rather than 404
    because the caller deliberately picked this chapter — they know
    it exists, so we can be honest about why we're rejecting it.

    A personal tenant has no chapters, so ``None`` is the only allowed
    value there and anything else is a malformed request (422) rather
    than a permission problem — there is no chapter it could have
    meant."""
    if is_personal(db, user):
        if chapter_id is not None:
            raise HTTPException(
                status_code=422,
                detail="This account has no chapters, so nothing can be assigned to one.",
            )
        return
    if chapter_id is None:
        # An organisation's entities always belong to one of its
        # chapters — the schema can't require it (a personal tenant
        # posts the same body without one), so the rule lives here.
        raise HTTPException(status_code=422, detail="Pick a chapter for this.")
    if chapter_id not in chapter_ids_for_user(db, user):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to that chapter",
        )


# --- Per-entity wrappers ---------------------------------------------
# One-liners over the generic helpers so call sites read naturally
# and the scope rule stays single-sourced above.


def event_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Event)


def get_event_for_user(db: Session, event_id: str, user: User) -> Event:
    return get_scoped(db, Event, event_id, user, not_found="Event not found")


def form_scope_filter(db: Session, user: User, mode: str) -> ColumnElement[bool]:
    """Scoped to the caller *and* to one of the two products the forms
    table holds. The mode has no default on purpose: a caller has to
    say which one it means (docs/design-quizzes.md)."""
    return and_(scope_filter(db, user, Form), Form.mode == mode)


def get_form_for_user(db: Session, form_id: str, user: User, mode: str) -> Form:
    return get_scoped(db, Form, form_id, user, not_found="Form not found", where=Form.mode == mode)


def datepoll_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Datepoll)


def get_datepoll_for_user(db: Session, datepoll_id: str, user: User) -> Datepoll:
    return get_scoped(db, Datepoll, datepoll_id, user, not_found="Datepoll not found")


def roster_scope_filter(db: Session, user: User) -> ColumnElement[bool]:
    return scope_filter(db, user, Roster)


def get_roster_for_user(db: Session, roster_id: str, user: User) -> Roster:
    return get_scoped(db, Roster, roster_id, user, not_found="Roster not found")
