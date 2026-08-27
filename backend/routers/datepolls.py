"""Chapter-scoped datepoll CRUD + organiser-side reads.

Mirrors the events/forms router shape: create, list active, list
archived, get, update, archive, restore, delete-when-archived,
summary, submissions. All require an approved user; all are scoped to
the user's chapter via ``access.get_datepoll_for_user`` (single) or
``access.list_filter`` (lists).

Public-by-slug surfaces live in ``routers/datepolls_public.py``.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..config import settings
from ..database import get_db
from ..models import Datepoll, DatepollSubmission, User
from ..schemas.common import EditLinkRecoverOut
from ..schemas.datepolls import (
    DatepollCreate,
    DatepollListOut,
    DatepollOut,
    DatepollSubmissionOut,
    DatepollSummaryOut,
    DatepollUpdate,
)
from ..services import access, crud, edit_token, entities, limits
from ..services import datepolls as datepolls_svc
from ..services import image as image_svc
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/datepolls", tags=["datepolls"])


@router.post("", response_model=DatepollOut, status_code=201)
@limiter.limit(Limits.ORG_RARE)
def create_datepoll(
    request: Request,
    data: DatepollCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    """Create a poll. Candidate slots are optional at create — a blank
    poll can be saved and slots added on the edit page. The
    caller-supplied ``chapter_id`` must be in the user's set."""
    access.assert_user_can_assign_chapter(db, user, data.chapter_id)
    limits.assert_can_add_entity(db, user.tenant, "datepoll")
    poll = entities.create_datepoll(db, data, user)
    db.commit()
    db.refresh(poll)
    return datepolls_svc.to_out(db, poll)


@router.get("", response_model=list[DatepollListOut])
def list_datepolls(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[DatepollListOut]:
    rows = (
        db.query(Datepoll)
        .filter(access.list_filter(db, user, Datepoll, chapter_id), Datepoll.archived_at.is_(None))
        .order_by(Datepoll.created_at.desc())
        .all()
    )
    return datepolls_svc.enrich(db, rows)


@router.get("/archived", response_model=list[DatepollListOut])
def list_archived_datepolls(
    chapter_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[DatepollListOut]:
    rows = (
        db.query(Datepoll)
        .filter(access.list_filter(db, user, Datepoll, chapter_id), Datepoll.archived_at.is_not(None))
        .order_by(Datepoll.archived_at.desc())
        .all()
    )
    return datepolls_svc.enrich(db, rows)


@router.get("/{datepoll_id}", response_model=DatepollOut)
def get_datepoll(
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    return datepolls_svc.to_out(db, poll)


@router.put("/{datepoll_id}", response_model=DatepollOut)
@limiter.limit(Limits.ORG_WRITE)
def update_datepoll(
    request: Request,
    datepoll_id: str,
    data: DatepollUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    """Update a poll. Chapter changes are allowed but the new one must
    be in the user's set. Slots are diff-applied on
    ``(on_date, start_time, end_time)`` — see
    ``services/datepolls.apply_slots``."""
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    if data.chapter_id != poll.chapter_id:
        access.assert_user_can_assign_chapter(db, user, data.chapter_id)

    poll.name_nl = data.name_nl
    poll.name_en = data.name_en
    poll.description_nl = data.description_nl
    poll.description_en = data.description_en
    poll.location = data.location
    poll.latitude = data.latitude
    poll.longitude = data.longitude
    poll.image_artist_instagram = data.image_artist_instagram
    poll.chapter_id = data.chapter_id
    poll.locale = data.locale
    poll.name_required = data.name_required
    poll.answers_editable = data.answers_editable
    datepolls_svc.apply_slots(db, poll.id, data.slots)
    db.commit()
    db.refresh(poll)
    logger.info("datepoll_updated", datepoll_id=poll.id, actor_id=user.id)
    return datepolls_svc.to_out(db, poll)


@router.post("/{datepoll_id}/archive", response_model=DatepollOut)
@limiter.limit(Limits.ORG_RARE)
def archive_datepoll(
    request: Request,
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    crud.archive(db, poll, log_event="datepoll_archived", actor_id=user.id)
    return datepolls_svc.to_out(db, poll)


@router.post("/{datepoll_id}/restore", response_model=DatepollOut)
@limiter.limit(Limits.ORG_RARE)
def restore_datepoll(
    request: Request,
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    crud.restore(db, poll, log_event="datepoll_restored", actor_id=user.id)
    return datepolls_svc.to_out(db, poll)


@router.delete("/{datepoll_id}", status_code=204)
@limiter.limit(Limits.ORG_RARE)
def delete_datepoll(
    request: Request,
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> None:
    """Hard-delete an archived poll. Refuses unless archived first —
    deleting a live poll with responses would be a data-loss footgun.
    Cascades through dates / submissions / responses via the FK
    ON DELETE CASCADEs."""
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    crud.hard_delete(
        db,
        poll,
        log_event="datepoll_deleted",
        actor_id=user.id,
        conflict_detail="Archive the datepoll before deleting it",
    )


@router.post("/{datepoll_id}/image", response_model=DatepollOut)
@limiter.limit(Limits.ORG_RARE)
async def upload_datepoll_image(
    request: Request,
    datepoll_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    """Upload (or replace) the poll's hero image — same 4:5 GitHub
    pipeline as events (``services/image.py``)."""
    if not settings.event_images_enabled:
        raise HTTPException(status_code=503, detail="Image storage is not configured")
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    raw = await file.read()
    timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
    try:
        poll.image_path = image_svc.replace_entity_image(
            folder="datepolls",
            entity_id=poll.id,
            raw=raw,
            timestamp_ms=timestamp_ms,
            previous=poll.image_path,
        )
    except image_svc.ImageProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except image_svc.GithubUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(poll)
    logger.info("datepoll_image_uploaded", datepoll_id=poll.id, actor_id=user.id)
    return datepolls_svc.to_out(db, poll)


@router.delete("/{datepoll_id}/image", response_model=DatepollOut)
@limiter.limit(Limits.ORG_RARE)
def delete_datepoll_image(
    request: Request,
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollOut:
    """Clear the reference and delete the file: nothing else points at
    it."""
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    if poll.image_path is None:
        raise HTTPException(status_code=404, detail="No image to delete")
    dropped = poll.image_path
    poll.image_path = None
    db.commit()
    image_svc.delete(dropped)
    db.refresh(poll)
    logger.info("datepoll_image_deleted", datepoll_id=poll.id, actor_id=user.id)
    return datepolls_svc.to_out(db, poll)


@router.get("/{datepoll_id}/summary", response_model=DatepollSummaryOut)
def datepoll_summary(
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> DatepollSummaryOut:
    access.get_datepoll_for_user(db, datepoll_id, user)
    slots, best_slot_id = datepolls_svc.slot_aggregates(db, datepoll_id)
    return DatepollSummaryOut(
        submission_count=datepolls_svc.submission_count(db, datepoll_id),
        slots=slots,
        best_slot_id=best_slot_id,
    )


@router.post("/{datepoll_id}/submissions/{submission_id}/edit-link", response_model=EditLinkRecoverOut)
@limiter.limit(Limits.ORG_WRITE)
def recover_submission_edit_link(
    request: Request,
    datepoll_id: str,
    submission_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> EditLinkRecoverOut:
    """Organiser recovery of a respondent's lost magic link — rotates
    the token (never reveals it) and permanently stamps
    ``link_recovered_at``; see ``services/edit_token.recover``."""
    poll = access.get_datepoll_for_user(db, datepoll_id, user)
    sub = (
        db.query(DatepollSubmission)
        .filter(DatepollSubmission.id == submission_id, DatepollSubmission.datepoll_id == poll.id)
        .first()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    raw = edit_token.recover(sub)
    db.commit()
    logger.info("datepoll_edit_link_recovered", datepoll_id=poll.id, submission_id=submission_id, actor_id=user.id)
    return EditLinkRecoverOut(edit_token=raw)


@router.get("/{datepoll_id}/submissions", response_model=list[DatepollSubmissionOut])
def datepoll_submissions(
    datepoll_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[DatepollSubmissionOut]:
    """Per-submission rows, keyed by slot id. CSV source.

    Privacy: the submission id is opaque and the only respondent
    identifier is the self-chosen pseudonym."""
    access.get_datepoll_for_user(db, datepoll_id, user)
    return datepolls_svc.submissions(db, datepoll_id)
