"""Public + organiser-side feedback endpoints.

Privacy contract: the only thing that links a response back to a
specific attendee is the ``FeedbackToken`` row, and that row is deleted
the moment the response is submitted. After redemption the system can
only see "someone who got the email for event X said Y". Never asked,
never stored: who that someone was.
"""

import secrets
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..auth import require_approved
from ..database import get_db
from ..models import Event, FeedbackQuestion, FeedbackResponse, FeedbackToken, Signup, User
from ..services import scd2 as scd2_svc
from ..services.rate_limit import limiter
from ..schemas.feedback import (
    EmailHealthOut,
    FeedbackFormOut,
    FeedbackQuestionOut,
    FeedbackQuestionSummary,
    FeedbackSubmissionOut,
    FeedbackSubmitIn,
    FeedbackSummaryOut,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["feedback"])


def _ordered_questions(db: Session) -> list[FeedbackQuestion]:
    return db.query(FeedbackQuestion).order_by(FeedbackQuestion.ordinal).all()


def _resolve_token(db: Session, token: str) -> FeedbackToken:
    row = db.query(FeedbackToken).filter(FeedbackToken.token == token).first()
    if not row:
        # 410 Gone matches the contract: the token may exist on a printed
        # email but is no longer redeemable (already used, expired, or
        # the send failed and we deleted it).
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    # SQLAlchemy returns naive datetimes from SQLite; the worker writes
    # tz-aware UTC. Normalise to a naive UTC for the comparison.
    expires = row.expires_at.replace(tzinfo=None) if row.expires_at.tzinfo else row.expires_at
    if expires <= datetime.now(UTC).replace(tzinfo=None):
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
    db: Session = Depends(get_db),
    _user: User = Depends(require_approved),
) -> list[FeedbackQuestionOut]:
    """The fixed-set questionnaire, used by the organiser-side preview page."""
    return [FeedbackQuestionOut.model_validate(q) for q in _ordered_questions(db)]


# --- Public: questionnaire form + submission --------------------------


@router.get("/feedback/{token}", response_model=FeedbackFormOut)
def get_feedback_form(token: str, db: Session = Depends(get_db)) -> FeedbackFormOut:
    row = _resolve_token(db, token)
    event = scd2_svc.current_by_entity(db, row.event_id)
    if not event:
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    questions = _ordered_questions(db)
    return FeedbackFormOut(
        event_name=event.name,
        event_slug=event.slug,
        event_locale=event.locale,
        questions=[FeedbackQuestionOut.model_validate(q) for q in questions],
    )


@router.post("/feedback/{token}/submit", status_code=201)
@limiter.limit("20/hour")
def submit_feedback(
    request: Request,
    token: str,
    data: FeedbackSubmitIn,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    row = _resolve_token(db, token)
    questions = {q.id: q for q in _ordered_questions(db)}

    # Validate every required question has a non-null answer of the right type.
    submitted_by_q: dict[str, object] = {}
    for ans in data.answers:
        q = questions.get(ans.question_id)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        if q.kind == "rating":
            if ans.answer_int is None:
                continue  # treat missing as skipped, validate required below
            submitted_by_q[q.id] = ans.answer_int
        elif q.kind == "text":
            text = (ans.answer_text or "").strip()
            if not text:
                continue
            submitted_by_q[q.id] = text
        else:
            raise HTTPException(status_code=500, detail=f"Unknown question kind: {q.kind}")

    for q in questions.values():
        if q.required and q.id not in submitted_by_q:
            raise HTTPException(status_code=400, detail=f"Question {q.key} is required.")

    submission_id = secrets.token_urlsafe(16)
    for q_id, value in submitted_by_q.items():
        q = questions[q_id]
        db.add(
            FeedbackResponse(
                event_id=row.event_id,
                question_id=q.id,
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


@router.get("/events/{entity_id}/feedback-summary", response_model=FeedbackSummaryOut)
def feedback_summary(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> FeedbackSummaryOut:
    # Mirror the events router's afdeling scoping — events outside the
    # user's afdeling 404 (don't leak existence).
    afdeling_match = (
        Event.afdeling_id == user.afdeling_id
        if user.afdeling_id is not None
        else Event.afdeling_id == "__no_match__"
    )
    event = (
        scd2_svc.current(db.query(Event))
        .filter(Event.entity_id == entity_id, afdeling_match)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    submission_count = (
        db.query(func.count(distinct(FeedbackResponse.submission_id)))
        .filter(FeedbackResponse.event_id == entity_id)
        .scalar()
        or 0
    )
    signup_count = (
        db.query(func.count(Signup.id)).filter(Signup.event_id == entity_id).scalar() or 0
    )
    rate = (submission_count / signup_count) if signup_count else 0.0

    health_rows = (
        db.query(Signup.feedback_email_status, func.count(Signup.id))
        .filter(Signup.event_id == entity_id)
        .group_by(Signup.feedback_email_status)
        .all()
    )
    health_counts: dict[str, int] = {status: int(count) for status, count in health_rows}
    email_health = EmailHealthOut(
        not_applicable=health_counts.get("not_applicable", 0),
        pending=health_counts.get("pending", 0),
        sent=health_counts.get("sent", 0),
        bounced=health_counts.get("bounced", 0),
        complaint=health_counts.get("complaint", 0),
        failed=health_counts.get("failed", 0),
    )

    questions = _ordered_questions(db)
    summaries: list[FeedbackQuestionSummary] = []
    for q in questions:
        if q.kind == "rating":
            rows = (
                db.query(FeedbackResponse.answer_int, func.count(FeedbackResponse.id))
                .filter(
                    FeedbackResponse.event_id == entity_id,
                    FeedbackResponse.question_id == q.id,
                    FeedbackResponse.answer_int.is_not(None),
                )
                .group_by(FeedbackResponse.answer_int)
                .all()
            )
            distribution = [0, 0, 0, 0, 0]
            total = 0
            weighted = 0
            for value, count in rows:
                idx = int(value) - 1
                if 0 <= idx < 5:
                    distribution[idx] = int(count)
                    total += int(count)
                    weighted += int(value) * int(count)
            avg = (weighted / total) if total else None
            summaries.append(
                FeedbackQuestionSummary(
                    question_id=q.id,
                    key=q.key,
                    kind="rating",
                    response_count=total,
                    rating_distribution=distribution,
                    rating_average=avg,
                )
            )
        else:
            texts = (
                db.query(FeedbackResponse.answer_text)
                .filter(
                    FeedbackResponse.event_id == entity_id,
                    FeedbackResponse.question_id == q.id,
                    FeedbackResponse.answer_text.is_not(None),
                )
                .order_by(FeedbackResponse.created_at.desc())
                .all()
            )
            summaries.append(
                FeedbackQuestionSummary(
                    question_id=q.id,
                    key=q.key,
                    kind="text",
                    response_count=len(texts),
                    texts=[t[0] for t in texts],
                )
            )

    return FeedbackSummaryOut(
        submission_count=submission_count,
        signup_count=signup_count,
        response_rate=rate,
        email_health=email_health,
        questions=summaries,
    )


@router.get("/events/{entity_id}/feedback-submissions", response_model=list[FeedbackSubmissionOut])
def feedback_submissions(
    entity_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> list[FeedbackSubmissionOut]:
    """Per-submission feedback rows. One entry per ``submission_id``,
    keyed by question ``key`` (so a CSV consumer can index by
    question without joining to the questions table). Used by the
    organiser-side CSV export.

    Privacy: the ``submission_id`` is a random per-submission token
    with no link back to the signup that produced it — this matches
    the contract documented in the public privacy notice."""
    # Same afdeling-scoping as the summary endpoint.
    afdeling_match = (
        Event.afdeling_id == user.afdeling_id
        if user.afdeling_id is not None
        else Event.afdeling_id == "__no_match__"
    )
    event = (
        scd2_svc.current(db.query(Event))
        .filter(Event.entity_id == entity_id, afdeling_match)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    questions_by_id = {q.id: q for q in _ordered_questions(db)}
    rows = (
        db.query(FeedbackResponse)
        .filter(FeedbackResponse.event_id == entity_id)
        .order_by(FeedbackResponse.submission_id, FeedbackResponse.created_at)
        .all()
    )

    grouped: dict[str, dict[str, int | str]] = {}
    for r in rows:
        q = questions_by_id.get(r.question_id)
        if q is None:
            continue
        bucket = grouped.setdefault(r.submission_id, {})
        if q.kind == "rating" and r.answer_int is not None:
            bucket[q.key] = r.answer_int
        elif q.kind == "text" and r.answer_text is not None:
            bucket[q.key] = r.answer_text

    return [
        FeedbackSubmissionOut(submission_id=sid, answers=ans)
        for sid, ans in grouped.items()
    ]
