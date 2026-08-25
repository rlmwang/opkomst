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
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Datepoll, Event, Form, Roster
from . import image as image_svc
from . import tenancy

logger = structlog.get_logger()

# How long an archived entity keeps its picture. Long enough that
# archiving is still an undo, short enough that a finished season
# clears itself out.
GRACE: Final[timedelta] = timedelta(days=21)

_MODELS: Final[tuple[type, ...]] = (Event, Form, Datepoll, Roster)


def _sweep(db: Session, model: type, cutoff: datetime) -> int:
    rows = (
        db.query(model)
        .filter(
            model.archived_at.is_not(None),
            model.archived_at < cutoff,
            model.image_path.is_not(None),
        )
        .all()
    )
    removed = 0
    for row in rows:
        path = row.image_path
        if not image_svc.delete(path):
            # Logged inside ``delete``. Leave the row pointing at the
            # file so the next sweep finds it again.
            continue
        # The tenant this row belongs to, because clearing the column is
        # a write and the flush guard checks who it is for.
        with tenancy.use(row.tenant_id, row.tenant.brand_slug):
            row.image_path = None
            db.commit()
        removed += 1
    return removed


def reap_images() -> int:
    """Delete the images of everything archived longer than ``GRACE``.
    Returns how many were removed, for the cron log."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(UTC) - GRACE
        removed = sum(_sweep(db, model, cutoff) for model in _MODELS)
        logger.info("images_reaped", removed=removed, grace_days=GRACE.days)
        return removed
    finally:
        db.close()
