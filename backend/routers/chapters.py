"""Chapters — admin-managed local chapters.

The list endpoint is open to every approved user (organisers need it
to see their own chapter and pick a label on the dashboard). Create /
archive / restore are admin-only.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin, require_approved
from ..database import get_db
from ..models import Chapter, Event, User
from ..schemas.chapters import (
    ChapterArchiveRequest,
    ChapterCreate,
    ChapterOut,
    ChapterPatch,
    ChapterUsageOut,
)
from ..services import chapters as svc
from ..services import scd2

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chapters", tags=["chapters"])


def _to_out(row: Chapter) -> ChapterOut:
    return ChapterOut(
        id=row.entity_id,
        name=row.name,
        archived=row.valid_until is not None,
        city=row.city,
        city_lat=row.city_lat,
        city_lon=row.city_lon,
    )


@router.get("", response_model=list[ChapterOut])
def list_chapters(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_approved),
) -> list[ChapterOut]:
    """List chapters. By default only active ones; pass
    ``include_archived=true`` to also surface soft-deleted ones (used
    by the admin autocomplete to support restore)."""
    rows = svc.latest_versions(db, include_archived=include_archived)
    return [_to_out(r) for r in rows]


@router.post("", response_model=ChapterOut, status_code=201)
def create_chapter(
    data: ChapterCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    name = svc.normalise_name(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if svc.name_exists_active(db, name):
        raise HTTPException(status_code=409, detail="A chapter with that name already exists")
    row = svc.create(db, name=name, changed_by=admin.entity_id)
    db.commit()
    logger.info("chapter_created", entity_id=row.entity_id, actor_id=admin.entity_id)
    return _to_out(row)


@router.patch("/{entity_id}", response_model=ChapterOut)
def patch_chapter(
    entity_id: str,
    data: ChapterPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    """Partial SCD2 update for the chapter — name and/or city. The
    city tuple is set together (display name + lat + lon); leaving
    all three at ``None`` in the payload clears a previously-set
    city. Pass nothing for ``city*`` keys to leave the current city
    untouched."""
    set_city = any(field in data.model_fields_set for field in ("city", "city_lat", "city_lon"))
    try:
        row = svc.update(
            db,
            entity_id=entity_id,
            changed_by=admin.entity_id,
            name=data.name,
            city=data.city,
            city_lat=data.city_lat,
            city_lon=data.city_lon,
            set_city=set_city,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    db.commit()
    logger.info("chapter_patched", entity_id=entity_id, actor_id=admin.entity_id)
    return _to_out(row)


@router.get("/{entity_id}/usage", response_model=ChapterUsageOut)
def chapter_usage(
    entity_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ChapterUsageOut:
    """How many users + events are currently linked to this chapter.
    The frontend calls this before opening the delete dialog so it
    can offer reassignment dropdowns when there's something at stake."""
    users = scd2.current(db.query(User)).filter(User.chapter_id == entity_id).count()
    events = scd2.current(db.query(Event)).filter(Event.chapter_id == entity_id).count()
    return ChapterUsageOut(users=users, events=events)


@router.delete("/{entity_id}", status_code=200, response_model=ChapterOut)
def archive_chapter(
    entity_id: str,
    data: ChapterArchiveRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    # Optional reassignment of dependents BEFORE we close the chapter.
    # The admin can choose to leave users / events orphaned (they stay
    # linked, become invisible / unable-to-act until the chapter is
    # restored). Both are nullable; neither is required.
    if data is not None:
        if data.reassign_users_to:
            target = svc.find_current_by_entity(db, data.reassign_users_to)
            if target is None or target.entity_id == entity_id:
                raise HTTPException(status_code=400, detail="Invalid reassign_users_to target")
            for u in scd2.current(db.query(User)).filter(User.chapter_id == entity_id).all():
                scd2.scd2_update(
                    db, u, changed_by=admin.entity_id, chapter_id=data.reassign_users_to
                )
        if data.reassign_events_to:
            target = svc.find_current_by_entity(db, data.reassign_events_to)
            if target is None or target.entity_id == entity_id:
                raise HTTPException(status_code=400, detail="Invalid reassign_events_to target")
            for e in scd2.current(db.query(Event)).filter(Event.chapter_id == entity_id).all():
                scd2.scd2_update(
                    db, e, changed_by=admin.entity_id, chapter_id=data.reassign_events_to
                )

    row = svc.archive(db, entity_id=entity_id, changed_by=admin.entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    db.commit()
    logger.info(
        "chapter_archived",
        entity_id=entity_id,
        actor_id=admin.entity_id,
        reassign_users_to=data.reassign_users_to if data else None,
        reassign_events_to=data.reassign_events_to if data else None,
    )
    return _to_out(row)


@router.post("/{entity_id}/restore", response_model=ChapterOut)
def restore_chapter(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    try:
        row = svc.restore(db, entity_id=entity_id, changed_by=admin.entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    logger.info("chapter_restored", entity_id=entity_id, actor_id=admin.entity_id)
    return _to_out(row)
