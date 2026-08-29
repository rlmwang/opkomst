"""Archive / restore / hard-delete for the archivable org entities.

Event, Form, Datepoll and Roster share these three operations, and the
router keeps only the access-checked lookup and the entity-specific
``to_out`` projection. The middle — the guard, the move, the commit and
the structured log — is here.

**Archiving is a move.** The entity and everything under it leave the
live tables for their twins (``services/archive.py``), and an
``ArchiveIndex`` row records what was archived and when. The live tables
then hold only live data: an archive that grows for ever does not make
every live query slower, and nothing has to remember to filter it out.

That changes one thing a caller can see. Archiving something twice used
to be a 409, because the row was still there with a date on it. It is a
404 now: the second call cannot find a live entity to archive, which is
the truth. Restoring something that is not archived is a 404 for the
same reason.

The response is built before the move, because after it there is no live
row to project.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import ArchiveIndex
from . import archive
from . import image as image_svc

logger = structlog.get_logger()


def archive_entity(db: Session, entity: Any, *, root: str, log_event: str, actor_id: str) -> None:
    """Move ``entity`` and its children into the archive."""
    entity_id = entity.id
    db.add(ArchiveIndex(root=root, entity_id=entity_id, archived_at=datetime.now(UTC)))
    db.flush()
    archive.archive_item(db, root, entity_id)
    db.commit()
    logger.info(log_event, entity_id=entity_id, actor_id=actor_id)


def restore_entity(db: Session, *, root: str, entity_id: str, log_event: str, actor_id: str) -> None:
    """Move an archived item back. 404 if the archive has no such item —
    it was never archived, or somebody else restored it first."""
    index = _index_row(db, root, entity_id)
    archive.restore_item(db, root, entity_id)
    db.delete(index)
    db.commit()
    logger.info(log_event, entity_id=entity_id, actor_id=actor_id)


def purge_entity(
    db: Session, *, root: str, entity_id: str, image_path: str | None, log_event: str, actor_id: str
) -> None:
    """Delete an archived item outright, and the image it owned.

    The image has to go here because nothing else can: ``image_reaper``
    finds pictures by reading the rows that point at them, and this is
    the call that removes the last row holding the path. Rows first,
    file second — a failed file delete costs storage, while clearing the
    row first would leave a file nothing can ever find again.
    """
    index = _index_row(db, root, entity_id)
    archive.purge_item(db, root, entity_id)
    db.delete(index)
    db.commit()
    if image_path:
        image_svc.delete(image_path)
    logger.info(log_event, entity_id=entity_id, actor_id=actor_id)


def _index_row(db: Session, root: str, entity_id: str) -> ArchiveIndex:
    row = db.query(ArchiveIndex).filter(ArchiveIndex.root == root, ArchiveIndex.entity_id == entity_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
