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
from ..schemas.datepolls import DatepollSubmitIn, PublicDatepollOut
from ..services import datepolls as datepolls_svc
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


@router.post("/by-slug/{slug}/submit", status_code=201)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def submit_datepoll(
    request: Request,
    slug: str,
    data: DatepollSubmitIn,
    db: Session = Depends(get_db),
) -> Response:
    """Accept one public submission. Each answer's ``datepoll_date_id``
    must belong to this poll; availability is constrained to the
    tri-state at the schema layer. Duplicate dates collapse (last
    wins). At least one answered date is required.

    Returns a bare 201 — nothing identifies the submission to the
    client; there is no read-back endpoint."""
    poll = _resolve_datepoll(db, slug)
    valid_date_ids = {row[0] for row in db.query(DatepollDate.id).filter(DatepollDate.datepoll_id == poll.id).all()}

    # Collapse duplicate dates (last wins) and validate membership.
    by_date: dict[str, tuple[str, str | None]] = {}
    for ans in data.answers:
        if ans.datepoll_date_id not in valid_date_ids:
            raise HTTPException(status_code=400, detail="Unknown datepoll_date_id")
        comment = (ans.comment or "").strip() or None
        by_date[ans.datepoll_date_id] = (ans.availability, comment)

    if not by_date:
        raise HTTPException(status_code=400, detail="Pick a state for at least one date.")

    submission = DatepollSubmission(datepoll_id=poll.id, display_name=data.display_name)
    db.add(submission)
    db.flush()  # need submission.id for the response rows
    for date_id, (availability, comment) in by_date.items():
        db.add(
            DatepollResponse(
                submission_id=submission.id,
                datepoll_date_id=date_id,
                availability=availability,
                comment=comment,
            )
        )

    db.commit()
    logger.info("datepoll_submitted", datepoll_id=poll.id, submission_id=submission.id, answers=len(by_date))
    return Response(status_code=201)
