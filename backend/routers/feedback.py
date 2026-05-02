"""Public + organiser-side feedback endpoints.

Privacy contract: the only thing that links a response back to a
specific attendee is the ``FeedbackToken`` row, and that row is deleted
the moment the response is submitted. After redemption the system can
only see "someone who got the email for event X said Y". Never asked,
never stored: who that someone was.

The questionnaire itself is a Python constant
(``services.feedback_questions``); ``FeedbackResponse`` rows
reference questions by ``question_key`` (a stable string like
``"q1_overall"``), not by FK to a DB table. There is no questions
table.
"""

import secrets
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import (
    Event,
    FeedbackResponse,
    FeedbackToken,
    User,
)
from ..schemas.feedback import (
    FeedbackFormOut,
    FeedbackQuestionOut,
    FeedbackSubmissionOut,
    FeedbackSubmitIn,
    FeedbackSummaryOut,
)
from ..services import access, feedback_stats
from ..services.feedback_questions import BY_KEY, QUESTIONS
from ..services.rate_limit import Limits, limiter

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["feedback"])


def _question_dtos() -> list[FeedbackQuestionOut]:
    """Static questionnaire as the public DTO list. Iterates the
    in-code constant in ordinal order — no DB query."""
    return [
        FeedbackQuestionOut(
            key=q.key,
            ordinal=q.ordinal,
            kind=q.kind,
            required=q.required,
        )
        for q in QUESTIONS
    ]


def _resolve_token(db: Session, token: str) -> FeedbackToken:
    row = db.query(FeedbackToken).filter(FeedbackToken.token == token).first()
    if not row:
        # 410 Gone matches the contract: the token may exist on a printed
        # email but is no longer redeemable (already used, expired, or
        # the send failed and we deleted it).
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    if row.expires_at <= datetime.now(UTC):
        # Stale — clean up and refuse.
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=410, detail="This feedback link has expired.")
    return row


# --- Organiser: questionnaire preview list -----------------------------
# (Declared before the dynamic /feedback/{token} routes so FastAPI's
# path matching prefers the static path.)


@router.get("/feedback/questions", response_model=list[FeedbackQuestionOut])
def list_questions(
    _user: User = Depends(require_approved),
) -> list[FeedbackQuestionOut]:
    """The fixed-set questionnaire, used by the organiser-side preview page."""
    return _question_dtos()


# --- Public: questionnaire form + submission --------------------------


@router.get("/feedback/{token}", response_model=FeedbackFormOut)
def get_feedback_form(token: str, db: Session = Depends(get_db)) -> FeedbackFormOut:
    row = _resolve_token(db, token)
    event = db.query(Event).filter(Event.id == row.event_id).first()
    if not event:
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    return FeedbackFormOut(
        event_name=event.name,
        event_slug=event.slug,
        event_locale=event.locale,
        questions=_question_dtos(),
    )


@router.post("/feedback/{token}/submit", status_code=201)
@limiter.limit(Limits.PUBLIC_FEEDBACK)
def submit_feedback(
    request: Request,
    token: str,
    data: FeedbackSubmitIn,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = _resolve_token(db, token)

    # Validate every required question has a non-null answer of the
    # right type. ``BY_KEY`` is the in-code question table.
    submitted_by_key: dict[str, object] = {}
    for ans in data.answers:
        q = BY_KEY.get(ans.question_key)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_key")
        if q.kind == "rating":
            if ans.answer_int is None:
                continue  # treat missing as skipped, validate required below
            submitted_by_key[q.key] = ans.answer_int
        elif q.kind == "text":
            text = (ans.answer_text or "").strip()
            if not text:
                continue
            submitted_by_key[q.key] = text
        else:
            raise HTTPException(status_code=500, detail=f"Unknown question kind: {q.kind}")

    for q in QUESTIONS:
        if q.required and q.key not in submitted_by_key:
            raise HTTPException(status_code=400, detail=f"Question {q.key} is required.")

    submission_id = secrets.token_urlsafe(16)
    for key, value in submitted_by_key.items():
        q = BY_KEY[key]
        db.add(
            FeedbackResponse(
                event_id=row.event_id,
                question_key=key,
                submission_id=submission_id,
                answer_int=value if q.kind == "rating" else None,  # type: ignore[arg-type]
                answer_text=value if q.kind == "text" else None,  # type: ignore[arg-type]
            )
        )

    # One-shot: the token is gone the moment we accept a response. The
    # privacy invariant is that no row in the system can map this
    # submission back to the attendee from this point on.
    db.delete(row)
    db.commit()
    logger.info("feedback_submitted", event_id=row.event_id, submission_id=submission_id)
    return {"status": "ok"}


# --- Organiser: per-event feedback summary ----------------------------


@router.get("/events/{event_id}/feedback-summary", response_model=FeedbackSummaryOut)
def feedback_summary(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FeedbackSummaryOut:
    access.get_event_for_user(db, event_id, user)
    submissions = feedback_stats.submission_count(db, event_id)
    signups = feedback_stats.signup_count(db, event_id)
    rate = (submissions / signups) if signups else 0.0
    return FeedbackSummaryOut(
        submission_count=submissions,
        signup_count=signups,
        response_rate=rate,
        email_health=feedback_stats.email_health(db, event_id, signups),
        questions=feedback_stats.question_aggregates(db, event_id),
    )


@router.get("/events/{event_id}/feedback-submissions", response_model=list[FeedbackSubmissionOut])
def feedback_submissions(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[FeedbackSubmissionOut]:
    """Per-submission feedback rows. One entry per ``submission_id``,
    keyed by question ``key`` (so a CSV consumer can index by
    question without joining to a questions table — there is no
    questions table; the keys are app-level constants). Used by
    the organiser-side CSV export.

    Privacy: the ``submission_id`` is a random per-submission token
    with no link back to the signup that produced it — this matches
    the contract documented in the public privacy notice."""
    access.get_event_for_user(db, event_id, user)

    rows = (
        db.query(FeedbackResponse)
        .filter(FeedbackResponse.event_id == event_id)
        .order_by(FeedbackResponse.submission_id, FeedbackResponse.created_at)
        .all()
    )

    grouped: dict[str, dict[str, int | str]] = {}
    for r in rows:
        q = BY_KEY.get(r.question_key)
        if q is None:
            # Stale row from a since-removed question; skip.
            continue
        bucket = grouped.setdefault(r.submission_id, {})
        if q.kind == "rating" and r.answer_int is not None:
            bucket[q.key] = r.answer_int
        elif q.kind == "text" and r.answer_text is not None:
            bucket[q.key] = r.answer_text

    return [FeedbackSubmissionOut(submission_id=sid, answers=ans) for sid, ans in grouped.items()]
