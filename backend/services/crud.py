"""Archive / restore / hard-delete for the archivable org entities.

Event, Form, Datepoll, and Roster all soft-archive via an ``archived_at``
column and share the exact same archive/restore/delete semantics:

* archive — 409 if already archived, else stamp ``archived_at`` now;
* restore — 409 if not archived, else clear ``archived_at``;
* hard-delete — 409 unless archived first (deleting a live entity with
  dependents is a data-loss footgun), else delete (FK ``ON DELETE
  CASCADE`` takes the children with it, and this module takes the
  image).

The router keeps the access-checked lookup and the entity-specific
``to_out`` projection; only this shared middle (the guard + the
``archived_at`` flip + commit + structured log) lives here. The log
carries the entity id under a uniform ``entity_id`` key plus the
``log_event`` name the caller passes (``event_archived`` etc.).
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import image as image_svc

logger = structlog.get_logger()


def archive(db: Session, entity: Any, *, log_event: str, actor_id: str) -> None:
    """Soft-archive ``entity``. 409 if it's already archived."""
    if entity.archived_at is not None:
        raise HTTPException(status_code=409, detail="Already archived")
    entity.archived_at = datetime.now(UTC)
    db.commit()
    db.refresh(entity)
    logger.info(log_event, entity_id=entity.id, actor_id=actor_id)


def restore(db: Session, entity: Any, *, log_event: str, actor_id: str) -> None:
    """Restore an archived ``entity``. 409 if it isn't archived."""
    if entity.archived_at is None:
        raise HTTPException(status_code=409, detail="Not archived")
    entity.archived_at = None
    db.commit()
    db.refresh(entity)
    logger.info(log_event, entity_id=entity.id, actor_id=actor_id)


def hard_delete(db: Session, entity: Any, *, log_event: str, actor_id: str, conflict_detail: str) -> None:
    """Hard-delete an archived ``entity`` (cascades to its children) and
    the image it owns. 409 with ``conflict_detail`` if the entity isn't
    archived first.

    The image has to go here because nothing else can. ``image_reaper``
    sweeps the pictures of entities archived past its grace window, and
    it finds them by reading rows — once the row is deleted the path it
    held is gone, and the file stays in the image repository for ever.
    Deleting inside that window used to strand one every time.

    Row first, file second. A failed delete leaves a file nobody
    references, which costs storage; clearing the row before the file
    would be the same leak with no record of it."""
    if entity.archived_at is None:
        raise HTTPException(status_code=409, detail=conflict_detail)
    entity_id = entity.id
    image_path = getattr(entity, "image_path", None)
    db.delete(entity)
    db.commit()
    if image_path:
        image_svc.delete(image_path)
    logger.info(log_event, entity_id=entity_id, actor_id=actor_id)
