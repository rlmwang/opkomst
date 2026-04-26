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
from ..models import Afdeling, User
from ..schemas.afdelingen import AfdelingCreate, AfdelingOut
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


@router.delete("/{entity_id}", status_code=200, response_model=AfdelingOut)
def archive_afdeling(
    entity_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AfdelingOut:
    row = svc.archive(db, entity_id=entity_id, changed_by=admin.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Afdeling not found")
    db.commit()
    logger.info("afdeling_archived", entity_id=entity_id, actor_id=admin.id)
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
