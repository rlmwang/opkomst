"""Afdelingen — admin-managed local chapters.

The list endpoint is open to every approved user (organisers need it
to see their own afdeling and pick a label on the dashboard). Create /
archive / restore are admin-only.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import require_admin, require_approved
from ..database import get_db
from ..models import Afdeling, Event, User
from ..schemas.afdelingen import (
    AfdelingArchiveRequest,
    AfdelingCreate,
    AfdelingOut,
    AfdelingUsageOut,
)
from ..services import afdelingen as svc

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/afdelingen", tags=["afdelingen"])


def _to_out(row: Afdeling) -> AfdelingOut:
    return AfdelingOut(id=row.entity_id, name=row.name, archived=row.valid_until is not None)


@router.get("", response_model=list[AfdelingOut])
def list_afdelingen(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_approved),
) -> list[AfdelingOut]:
    """List afdelingen. By default only active ones; pass
    ``include_archived=true`` to also surface soft-deleted ones (used
    by the admin autocomplete to support restore)."""
    rows = svc.latest_versions(db, include_archived=include_archived)
    return [_to_out(r) for r in rows]


@router.post("", response_model=AfdelingOut, status_code=201)
def create_afdeling(
    data: AfdelingCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AfdelingOut:
    name = data.name.strip()
    if svc.name_exists_active(db, name):
        raise HTTPException(status_code=409, detail="An afdeling with that name already exists")
    row = svc.create(db, name=name, changed_by=admin.id)
    db.commit()
    logger.info("afdeling_created", entity_id=row.entity_id, actor_id=admin.id)
    return _to_out(row)


@router.patch("/{entity_id}", response_model=AfdelingOut)
def rename_afdeling(
    entity_id: str,
    data: AfdelingCreate,  # reuses the {name: str} shape
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AfdelingOut:
    """SCD2-update the chapter's name. Closes the current version and
    inserts a new row with the new name (same entity_id), so events /
    users tracking it follow automatically."""
    name = data.name.strip()
    try:
        row = svc.rename(db, entity_id=entity_id, name=name, changed_by=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Afdeling not found")
    db.commit()
    logger.info("afdeling_renamed", entity_id=entity_id, name=name, actor_id=admin.id)
    return _to_out(row)


@router.get("/{entity_id}/usage", response_model=AfdelingUsageOut)
def afdeling_usage(
    entity_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> AfdelingUsageOut:
    """How many users + events are currently linked to this chapter.
    The frontend calls this before opening the delete dialog so it
    can offer reassignment dropdowns when there's something at stake."""
    users = db.query(User).filter(User.afdeling_id == entity_id).count()
    events = db.query(Event).filter(Event.afdeling_id == entity_id).count()
    return AfdelingUsageOut(users=users, events=events)


@router.delete("/{entity_id}", status_code=200, response_model=AfdelingOut)
def archive_afdeling(
    entity_id: str,
    data: AfdelingArchiveRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AfdelingOut:
    # Optional reassignment of dependents BEFORE we close the
    # afdeling. The admin can choose to leave users / events orphaned
    # (they stay linked, become invisible / unable-to-act until the
    # chapter is restored). Both are nullable; neither is required.
    if data is not None:
        if data.reassign_users_to:
            target = svc.find_current_by_entity(db, data.reassign_users_to)
            if target is None or target.entity_id == entity_id:
                raise HTTPException(status_code=400, detail="Invalid reassign_users_to target")
            db.query(User).filter(User.afdeling_id == entity_id).update(
                {User.afdeling_id: data.reassign_users_to}, synchronize_session=False
            )
        if data.reassign_events_to:
            target = svc.find_current_by_entity(db, data.reassign_events_to)
            if target is None or target.entity_id == entity_id:
                raise HTTPException(status_code=400, detail="Invalid reassign_events_to target")
            db.query(Event).filter(Event.afdeling_id == entity_id).update(
                {Event.afdeling_id: data.reassign_events_to}, synchronize_session=False
            )

    row = svc.archive(db, entity_id=entity_id, changed_by=admin.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Afdeling not found")
    db.commit()
    logger.info(
        "afdeling_archived",
        entity_id=entity_id,
        actor_id=admin.id,
        reassign_users_to=data.reassign_users_to if data else None,
        reassign_events_to=data.reassign_events_to if data else None,
    )
    return _to_out(row)


@router.post("/{entity_id}/restore", response_model=AfdelingOut)
def restore_afdeling(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AfdelingOut:
    try:
        row = svc.restore(db, entity_id=entity_id, changed_by=admin.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    logger.info("afdeling_restored", entity_id=entity_id, actor_id=admin.id)
    return _to_out(row)
