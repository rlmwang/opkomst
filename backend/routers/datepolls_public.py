"""Public-by-slug surfaces for one datepoll.

Three endpoints, all keyed by the public 8-char slug, all
unauthenticated. Split out of the organiser router for the same
reason ``events_public`` / ``forms_public`` exist: zero shared auth +
scope code with the chapter-scoped CRUD.

* ``GET /by-slug/{slug}`` — the JSON the public poll reads.
* ``POST /by-slug/{slug}/submit`` — public submission. Rate-limited;
  anyone with the slug may submit. Returns a bare 201 — the opaque
  submission id is never handed back (data minimisation; there is no
  endpoint that resolves it).
* ``GET /by-slug/{slug}/qr.svg`` — QR resolving to ``/d/{slug}``.

Archived / unknown slugs 410 on the JSON + submit endpoints.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Datepoll, DatepollDate, DatepollResponse, DatepollSubmission
from ..schemas.datepolls import (
    DatepollEditOut,
    DatepollEditValue,
    DatepollSubmitAck,
    DatepollSubmitIn,
    PublicDatepollOut,
)
from ..services import datepolls as datepolls_svc
from ..services import edit_token
from ..services.qr import render_qr
from ..services.rate_limit import Limits, limiter

PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/datepolls", tags=["datepolls"])


def _resolve_datepoll(db: Session, slug: str) -> Datepoll:
    """Resolve a slug to a live poll. Archived + unknown both 410 —
    the public surface doesn't distinguish them (no info leak)."""
    poll = db.query(Datepoll).filter(Datepoll.slug == slug).first()
    if poll is None or poll.archived_at is not None:
        raise HTTPException(status_code=410, detail="This datepoll is no longer available.")
    return poll


@router.get("/by-slug/{slug}/qr.svg")
def get_datepoll_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    """QR SVG for one slug. Resolves the poll first so a typo'd slug
    410s rather than 200ing with a wrong-target QR."""
    poll = _resolve_datepoll(db, slug)
    return Response(
        content=render_qr(f"{PUBLIC_BASE_URL}/d/{poll.slug}"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}", response_model=PublicDatepollOut)
def get_public_datepoll(slug: str, db: Session = Depends(get_db)) -> PublicDatepollOut:
    return datepolls_svc.to_public_out(db, _resolve_datepoll(db, slug))


def _build_by_date(db: Session, poll_id: str, data: DatepollSubmitIn) -> dict[str, tuple[str, str | None]]:
    """Validate a submit/edit payload against the poll's dates →
    ``{date_id: (availability, comment)}``. Duplicate dates collapse
    (last wins); ≥1 answered date required. Shared by submit + edit."""
    valid_date_ids = {row[0] for row in db.query(DatepollDate.id).filter(DatepollDate.datepoll_id == poll_id).all()}
    by_date: dict[str, tuple[str, str | None]] = {}
    for ans in data.answers:
        if ans.datepoll_date_id not in valid_date_ids:
            raise HTTPException(status_code=400, detail="Unknown datepoll_date_id")
        comment = (ans.comment or "").strip() or None
        by_date[ans.datepoll_date_id] = (ans.availability, comment)
    if not by_date:
        raise HTTPException(status_code=400, detail="Pick a state for at least one date.")
    return by_date


def _write_responses(db: Session, submission_id: str, by_date: dict[str, tuple[str, str | None]]) -> None:
    for date_id, (availability, comment) in by_date.items():
        db.add(
            DatepollResponse(
                submission_id=submission_id,
                datepoll_date_id=date_id,
                availability=availability,
                comment=comment,
            )
        )


def _submission_by_token(db: Session, token: str) -> DatepollSubmission:
    """Resolve an edit-link token to its submission. 404 if no match;
    410 if the poll is no longer public (archived)."""
    sub = (
        db.query(DatepollSubmission)
        .filter(DatepollSubmission.edit_token_hash == edit_token.hash_edit_token(token))
        .first()
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="This edit link is not valid.")
    poll = db.query(Datepoll).filter(Datepoll.id == sub.datepoll_id).first()
    if poll is None or poll.archived_at is not None:
        raise HTTPException(status_code=410, detail="This datepoll is no longer available.")
    return sub


def _answers_for(db: Session, submission_id: str) -> dict[str, DatepollEditValue]:
    return {
        r.datepoll_date_id: DatepollEditValue(availability=r.availability, comment=r.comment)  # type: ignore[arg-type]
        for r in db.query(DatepollResponse).filter(DatepollResponse.submission_id == submission_id).all()
    }


@router.post("/by-slug/{slug}/submit", response_model=DatepollSubmitAck, status_code=201)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def submit_datepoll(
    request: Request,
    slug: str,
    data: DatepollSubmitIn,
    db: Session = Depends(get_db),
) -> DatepollSubmitAck:
    """Accept one public submission. Mints a secret edit-link token
    (raw returned once; only its hash stored) so the respondent can
    revisit and edit."""
    poll = _resolve_datepoll(db, slug)
    by_date = _build_by_date(db, poll.id, data)

    raw_token, token_hash = edit_token.new_edit_token()
    submission = DatepollSubmission(datepoll_id=poll.id, display_name=data.display_name, edit_token_hash=token_hash)
    db.add(submission)
    db.flush()
    _write_responses(db, submission.id, by_date)
    db.commit()
    logger.info("datepoll_submitted", datepoll_id=poll.id, submission_id=submission.id, answers=len(by_date))
    return DatepollSubmitAck(edit_token=raw_token)


@router.get("/by-token/{token}", response_model=DatepollEditOut)
def get_datepoll_submission(token: str, db: Session = Depends(get_db)) -> DatepollEditOut:
    """Current values of a submission, for pre-filling the edit form."""
    sub = _submission_by_token(db, token)
    return DatepollEditOut(display_name=sub.display_name, answers=_answers_for(db, sub.id))


@router.put("/by-token/{token}", response_model=DatepollEditOut)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def update_datepoll_submission(
    request: Request,
    token: str,
    data: DatepollSubmitIn,
    db: Session = Depends(get_db),
) -> DatepollEditOut:
    """Update a submission in place via its edit-link token. Replaces
    the per-date answers and the pseudonym."""
    sub = _submission_by_token(db, token)
    by_date = _build_by_date(db, sub.datepoll_id, data)
    db.query(DatepollResponse).filter(DatepollResponse.submission_id == sub.id).delete()
    sub.display_name = data.display_name
    _write_responses(db, sub.id, by_date)
    db.commit()
    logger.info("datepoll_submission_edited", datepoll_id=sub.datepoll_id, submission_id=sub.id)
    return DatepollEditOut(display_name=sub.display_name, answers=_answers_for(db, sub.id))
