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
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from uuid_utils import uuid7

from ..auth import require_approved
from ..database import get_db
from ..models import (
    FeedbackResponse,
    FeedbackToken,
    Occurrence,
    User,
)
from ..schemas.common import pick_localized
from ..schemas.feedback import (
    FeedbackFormOut,
    FeedbackQuestionOut,
    FeedbackSubmitIn,
    FeedbackSummaryOut,
)
from ..services import access, archive, csv_export, feedback_stats
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


@dataclass(frozen=True)
class _Redeemable:
    """A token that may still be spent, and where its rows live.

    ``archived`` is the whole difference between the two cases: an event
    archived while the feedback email sat in somebody's inbox has moved
    to the twins, so the occurrence is read from there and the response
    is written there. The person who was emailed keeps the right to
    answer that they earned when the mail was sent — archiving is an
    organiser tidying up, not a revocation."""

    token: str
    occurrence_id: str
    expires_at: datetime
    archived: bool


def _archived_tenant(db: Session, occurrence_id: str) -> str:
    """The tenant of an archived occurrence. Every row carries one, and
    a write on behalf of a visitor has no bound tenant to inherit."""
    row = archive.find_one(db, "occurrences", "id", occurrence_id)
    if row is None:
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    return row["tenant_id"]


def _resolve_token(db: Session, token: str) -> _Redeemable:
    row = db.query(FeedbackToken).filter(FeedbackToken.token == token).first()
    archived_row = None if row else archive.find_one(db, "feedback_tokens", "token", token)
    if not row and not archived_row:
        # 410 Gone matches the contract: the token may exist on a printed
        # email but is no longer redeemable (already used, expired, or
        # the send failed and we deleted it).
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    if row is not None:
        found = _Redeemable(token=token, occurrence_id=row.occurrence_id, expires_at=row.expires_at, archived=False)
    else:
        assert archived_row is not None  # the guard above proved it
        found = _Redeemable(
            token=token,
            occurrence_id=archived_row["occurrence_id"],
            expires_at=archived_row["expires_at"],
            archived=True,
        )
    if found.expires_at <= datetime.now(UTC):
        # Stale — clean up and refuse.
        _burn(db, found)
        db.commit()
        raise HTTPException(status_code=410, detail="This feedback link has expired.")
    return found


def _burn(db: Session, found: _Redeemable) -> None:
    """One-shot: the token stops existing, wherever it was."""
    if found.archived:
        archive.delete_row(db, "feedback_tokens", "token", found.token)
    else:
        db.query(FeedbackToken).filter(FeedbackToken.token == found.token).delete()


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
    found = _resolve_token(db, token)
    if found.archived:
        occurrence = archive.find_one(db, "occurrences", "id", found.occurrence_id)
        event = archive.find_one(db, "events", "id", occurrence["event_id"]) if occurrence else None
        if not occurrence or not event:
            raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
        return FeedbackFormOut(
            event_name=pick_localized(event["name_nl"], event["name_en"], event["locale"]) or "",
            event_slug=occurrence["slug"],
            event_locale=event["locale"],
            questions=_question_dtos(),
        )
    occurrence = db.query(Occurrence).filter(Occurrence.id == found.occurrence_id).first()
    if not occurrence:
        raise HTTPException(status_code=410, detail="This feedback link is no longer valid.")
    event = occurrence.event
    return FeedbackFormOut(
        event_name=pick_localized(event.name_nl, event.name_en, event.locale) or "",
        event_slug=occurrence.slug,
        event_locale=event.locale,
        questions=_question_dtos(),
    )


@router.post("/feedback/{token}/submit", status_code=201)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def submit_feedback(
    request: Request,
    token: str,
    data: FeedbackSubmitIn,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    found = _resolve_token(db, token)

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
        answer_int = value if q.kind == "rating" else None
        answer_text = value if q.kind == "text" else None
        if found.archived:
            # The event was archived while this link sat in an inbox, so
            # the answer belongs where the occurrence it answers lives.
            archive.add_row(
                db,
                "feedback_responses",
                {
                    "id": str(uuid7()),
                    "tenant_id": _archived_tenant(db, found.occurrence_id),
                    "occurrence_id": found.occurrence_id,
                    "question_key": key,
                    "submission_id": submission_id,
                    "answer_int": answer_int,
                    "answer_text": answer_text,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            continue
        db.add(
            FeedbackResponse(
                occurrence_id=found.occurrence_id,
                question_key=key,
                submission_id=submission_id,
                answer_int=answer_int,  # type: ignore[arg-type]
                answer_text=answer_text,  # type: ignore[arg-type]
            )
        )

    # One-shot: the token is gone the moment we accept a response. The
    # privacy invariant is that no row in the system can map this
    # submission back to the attendee from this point on.
    occurrence_id = found.occurrence_id
    _burn(db, found)
    db.commit()
    logger.info("feedback_submitted", occurrence_id=occurrence_id, submission_id=submission_id)
    return {"status": "ok"}


# --- Organiser: per-event feedback summary ----------------------------


@router.get("/event/{event_id}/feedback-summary", response_model=FeedbackSummaryOut)
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


@router.get("/event/{event_id}/feedback-submissions.csv", response_class=StreamingResponse)
def feedback_submissions_csv(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_approved),
) -> StreamingResponse:
    """The download: one row per submission, one column per question,
    written by the database and streamed straight out.

    The headers are English on every download
    (``services/csv_export``)."""
    event = access.get_event_for_user(db, event_id, user)
    header, rows = feedback_stats.submissions_csv(db, event_id)
    stem = csv_export.filename_slug(event.name_nl or event.name_en or "")
    return csv_export.csv_response(f"{event.starts_on}-{stem}-{event.id}.csv", header, rows)
