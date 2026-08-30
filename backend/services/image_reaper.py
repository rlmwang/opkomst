"""Delete the images of things nobody is coming back to.

An organiser archives a finished event and its picture stops being
looked at, but it stays stored for ever unless something removes it.
Archiving is reversible and organisers use it that way, so nothing is
deleted the moment it is archived: an entity archived longer than
``GRACE`` loses its image, and restoring inside that window still gets
the picture back.

Nothing live is ever touched. The images of entities that are still
active, and the images replaced or removed by hand, are handled where
they happen (``routers/*.py`` delete the file they orphan) — this sweep
is only about the ones archiving orphans quietly.

A failed delete is left for tomorrow: the file stays, the column stays
pointing at it, and the next sweep tries again. Clearing the column
before the file is gone would strand the file for ever, so the order is
delete first, then clear.
"""

from datetime import UTC, datetime, timedelta
from typing import Final

import structlog
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ArchiveIndex
from ..models.archive import ARCHIVABLE_ROOTS, archive_metadata
from . import image as image_svc

logger = structlog.get_logger()

# How long an archived entity keeps its picture. Long enough that
# archiving is still an undo, short enough that a finished season
# clears itself out.
GRACE: Final[timedelta] = timedelta(days=21)


def _sweep(db: Session, root: str, cutoff: datetime) -> int:
    """One root's twin: the pictures of items archived before ``cutoff``.

    Archiving is a move, so an archived item's row is in the twin and
    the date it was archived is in ``ArchiveIndex``. Nothing live is
    archived, so there is nothing to sweep on the live side.
    """
    twin = archive_metadata.tables[f"{root}_archive"]
    long_archived = select(ArchiveIndex.entity_id).where(
        ArchiveIndex.root == root,
        ArchiveIndex.archived_at < cutoff,
    )
    rows = db.execute(
        select(twin.c.id, twin.c.image_path).where(
            twin.c.image_path.is_not(None),
            twin.c.id.in_(long_archived),
        )
    ).all()
    removed = 0
    for row_id, path in rows:
        if not image_svc.delete(path):
            # Logged inside ``delete``. Leave the row pointing at the
            # file so the next sweep finds it again.
            continue
        db.execute(update(twin).where(twin.c.id == row_id).values(image_path=None))
        db.commit()
        removed += 1
    return removed


def reap_images() -> int:
    """Delete the images of everything archived longer than ``GRACE``.
    Returns how many were removed, for the cron log."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(UTC) - GRACE
        removed = sum(_sweep(db, root, cutoff) for root in ARCHIVABLE_ROOTS)
        logger.info("images_reaped", removed=removed, grace_days=GRACE.days)
        return removed
    finally:
        db.close()
