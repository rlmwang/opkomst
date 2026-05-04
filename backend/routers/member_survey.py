"""New-members feedback survey: public form + admin results.

Separate from the per-event ``feedback`` router: this is a
single, standalone questionnaire about activation of new
members, not tied to any event.

Privacy posture differs from event-feedback: this form does
collect a first name (optional). The intro copy makes that
visible. No email, no IP, no link to any User row.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import MemberSurveyResponse, User
from ..schemas.member_survey import (
    MemberSurveyFormOut,
    MemberSurveyResponseOut,
    MemberSurveyResultsOut,
    MemberSurveySubmitIn,
    RatingBreakdown,
)
from ..services.member_survey_questions import BARRIER_KEY_SET, BARRIER_KEYS
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/member-survey", tags=["member-survey"])


@router.get("/form", response_model=MemberSurveyFormOut)
def get_form() -> MemberSurveyFormOut:
    """Public: returns the static structure of the form. The
    client owns all rendering; this endpoint exists so the set
    of barrier keys stays a server-side constant the client
    cannot drift from."""
    return MemberSurveyFormOut(barriers=list(BARRIER_KEYS))


@router.post("/responses", status_code=201)
@limiter.limit(Limits.PUBLIC_FEEDBACK)
def submit_response(
    request: Request,
    data: MemberSurveySubmitIn,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # De-duplicate the multi-select; reject unknown keys explicitly
    # rather than silently dropping (drift would silently lose data).
    barriers = list(dict.fromkeys(data.q4_barriers))
    unknown = [b for b in barriers if b not in BARRIER_KEY_SET]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown barrier keys: {unknown}")

    first_name = (data.first_name or "").strip() or None
    other_text = (data.q4_other_text or "").strip() or None
    helps = (data.q5_helps or "").strip() or None

    row = MemberSurveyResponse(
        first_name=first_name,
        q1_connected=data.q1_connected,
        q2_clarity=data.q2_clarity,
        q3_likelihood=data.q3_likelihood,
        q4_barriers=barriers,
        q4_other_text=other_text,
        q5_helps=helps,
    )
    db.add(row)
    db.commit()
    logger.info("member_survey_submitted", response_id=row.id)
    return {"status": "ok"}


def _breakdown(rows: list[MemberSurveyResponse], attr: str) -> RatingBreakdown:
    distribution = [0, 0, 0, 0, 0]
    total = 0
    for r in rows:
        v = getattr(r, attr)
        if 1 <= v <= 5:
            distribution[v - 1] += 1
            total += v
    n = sum(distribution)
    return RatingBreakdown(
        average=(total / n) if n else None,
        distribution=distribution,
    )


@router.get("/results", response_model=MemberSurveyResultsOut)
def get_results(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> MemberSurveyResultsOut:
    """Admin-only aggregate of every response submitted so far.

    Returns the raw response list too — the volume is small
    (one questionnaire, occasional new-members days) and the
    admin page renders both rating bars + the per-respondent
    open-text answers from the same payload."""
    rows = db.query(MemberSurveyResponse).order_by(MemberSurveyResponse.created_at.desc()).all()

    barrier_counts: dict[str, int] = dict.fromkeys(BARRIER_KEYS, 0)
    for r in rows:
        for key in r.q4_barriers:
            if key in barrier_counts:
                barrier_counts[key] += 1

    return MemberSurveyResultsOut(
        response_count=len(rows),
        q1_connected=_breakdown(rows, "q1_connected"),
        q2_clarity=_breakdown(rows, "q2_clarity"),
        q3_likelihood=_breakdown(rows, "q3_likelihood"),
        barrier_counts=barrier_counts,
        responses=[MemberSurveyResponseOut.model_validate(r) for r in rows],
    )
