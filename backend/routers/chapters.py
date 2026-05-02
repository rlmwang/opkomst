"""Chapters — admin-managed local chapters.

The list endpoint is open to every approved user (organisers
need it to see their own chapter and pick a label on the
dashboard). Create / archive / restore are admin-only.

Error translation is uniform: every service helper raises either
``ChapterNotFound`` (→ 404) or ``ChapterRuleViolation`` (→ 409).
``_translate`` is the one place that mapping lives.
"""

from contextlib import contextmanager

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_admin, require_approved
from ..database import get_db
from ..models import Chapter, Event, User, UserChapter
from ..schemas.chapters import (
    ChapterArchiveRequest,
    ChapterCreate,
    ChapterOut,
    ChapterPatch,
    ChapterUsageOut,
)
from ..services import chapters as svc
from ..services.chapters import ChapterInvalidInput, ChapterNotFound, ChapterRuleViolation
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chapters", tags=["chapters"])


@contextmanager
def _translate():
    """Map service-layer typed exceptions to HTTP status codes.
    404 for a missing chapter, 409 for a state conflict (rule
    violation), 400 for invalid input (bad reassign target)."""
    try:
        yield
    except ChapterNotFound:
        raise HTTPException(status_code=404, detail="Chapter not found") from None
    except ChapterRuleViolation as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ChapterInvalidInput as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _to_out(row: Chapter) -> ChapterOut:
    return ChapterOut(
        id=row.id,
        name=row.name,
        archived=row.deleted_at is not None,
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
@limiter.limit(Limits.ORG_RARE)
def create_chapter(
    request: Request,
    data: ChapterCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    name = svc.normalise_name(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if svc.name_exists_active(db, name):
        raise HTTPException(status_code=409, detail="A chapter with that name already exists")
    row = svc.create(db, name=name)
    db.commit()
    logger.info("chapter_created", chapter_id=row.id, actor_id=admin.id)
    return _to_out(row)


@router.patch("/{chapter_id}", response_model=ChapterOut)
@limiter.limit(Limits.ORG_WRITE)
def patch_chapter(
    request: Request,
    chapter_id: str,
    data: ChapterPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    """Partial update — name and/or city. The city tuple is set
    together (display name + lat + lon); leaving all three at
    ``None`` in the payload clears a previously-set city. Pass
    nothing for ``city*`` keys to leave the current city
    untouched."""
    set_city = any(field in data.model_fields_set for field in ("city", "city_lat", "city_lon"))
    with _translate():
        row = svc.update(
            db,
            chapter_id=chapter_id,
            name=data.name,
            city=data.city,
            city_lat=data.city_lat,
            city_lon=data.city_lon,
            set_city=set_city,
        )
    db.commit()
    logger.info("chapter_patched", chapter_id=chapter_id, actor_id=admin.id)
    return _to_out(row)


@router.get("/{chapter_id}/usage", response_model=ChapterUsageOut)
def chapter_usage(
    chapter_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ChapterUsageOut:
    """How many live users + events are currently linked to this
    chapter. The frontend calls this before opening the delete
    dialog so it can offer reassignment dropdowns when there's
    something at stake."""
    # Live users with a membership row pointing at this chapter.
    # Soft-deleted users (``deleted_at IS NOT NULL``) don't count;
    # their membership rows persist so a re-registration restores
    # the relationship, but they aren't a present-day stakeholder.
    users = (
        db.query(UserChapter)
        .join(User, User.id == UserChapter.user_id)
        .filter(UserChapter.chapter_id == chapter_id, User.deleted_at.is_(None))
        .count()
    )
    events = db.query(Event).filter(Event.chapter_id == chapter_id).count()
    return ChapterUsageOut(users=users, events=events)


@router.delete("/{chapter_id}", status_code=200, response_model=ChapterOut)
@limiter.limit(Limits.ORG_RARE)
def archive_chapter(
    request: Request,
    chapter_id: str,
    data: ChapterArchiveRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    reassign_users_to = data.reassign_users_to if data else None
    reassign_events_to = data.reassign_events_to if data else None
    with _translate():
        row = svc.archive_with_reassign(
            db,
            chapter_id=chapter_id,
            reassign_users_to=reassign_users_to,
            reassign_events_to=reassign_events_to,
        )
    db.commit()
    logger.info(
        "chapter_archived",
        chapter_id=chapter_id,
        actor_id=admin.id,
        reassign_users_to=reassign_users_to,
        reassign_events_to=reassign_events_to,
    )
    return _to_out(row)


@router.post("/{chapter_id}/restore", response_model=ChapterOut)
@limiter.limit(Limits.ORG_RARE)
def restore_chapter(
    request: Request,
    chapter_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ChapterOut:
    with _translate():
        row = svc.restore(db, chapter_id=chapter_id)
    db.commit()
    logger.info("chapter_restored", chapter_id=chapter_id, actor_id=admin.id)
    return _to_out(row)
