"""Public-by-slug surfaces for one form.

Three endpoints, all keyed by the public 8-char slug, all
unauthenticated. Split out of the main forms router for the same
reason ``events_public.py`` exists: zero shared auth + scope code
with the chapter-scoped organiser CRUD, so keeping the two halves
together would invite a leaky-private mistake.

* ``GET /by-slug/{slug}`` — the JSON the public form reads.
* ``POST /by-slug/{slug}/submit`` — public submission. Rate-
  limited; anyone with the slug may submit; per-kind validation
  applies; the response is the random ``submission_id`` only
  (no link back to the submitter).
* ``GET /by-slug/{slug}/qr.svg`` — QR code that resolves to
  ``PUBLIC_BASE_URL/f/{slug}``. Mirrors the events QR endpoint
  one-to-one — same SVG-path rendering, same per-process LRU,
  same 24h browser cache.

Archived forms 410 on the JSON + submit endpoints; QR is served
for any live form (archived forms aren't displayed anywhere
that surfaces the QR).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Form, FormQuestion, FormResponse, FormSubmission
from ..schemas.forms import (
    FormAnswerIn,
    FormEditOut,
    FormSubmitAck,
    FormSubmitIn,
    PublicFormOut,
)
from ..services import edit_token, limits, public_access, traffic
from ..services import forms as forms_svc
from ..services.qr import render_qr
from ..services.rate_limit import Limits, limiter

# Public-facing base URL — validated at import time (HttpUrl),
# never empty. Same constant ``events_public.py`` uses.
PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/forms", tags=["forms"])


def _resolve_form(db: Session, slug: str) -> Form:
    """Resolve a slug to a live form. Archived forms 410. Unknown
    slugs 410 too — the public surface doesn't distinguish "never
    existed" from "archived since you bookmarked the link"; both
    look the same to the visitor and that's correct (no info
    leak)."""
    return public_access.resolve_by_slug(db, Form, slug, gone_detail="This form is no longer available.")


def _form_questions(db: Session, form_id: str) -> list[FormQuestion]:
    return db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()


@router.get("/by-slug/{slug}/qr.svg")
def get_form_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    """QR SVG for one slug. Resolves the form first so a typo'd
    slug 410s rather than 200ing with a wrong-target QR."""
    form = _resolve_form(db, slug)
    return Response(
        content=render_qr(f"{PUBLIC_BASE_URL}/f/{form.slug}"),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}", response_model=PublicFormOut)
def get_public_form(slug: str, db: Session = Depends(get_db)) -> PublicFormOut:
    return forms_svc.to_public_out(db, _resolve_form(db, slug))


def _build_submitted(questions: list[FormQuestion], answers: list[FormAnswerIn]) -> dict[str, dict[str, object]]:
    """Per-kind validation of a public answer payload → ``{question_id:
    fields}``. Skipped optional questions are absent; a skipped
    required question 400s. Shared by submit + edit."""
    by_id = {q.id: q for q in questions}
    submitted: dict[str, dict[str, object]] = {}
    for ans in answers:
        q = by_id.get(ans.question_id)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        if q.kind == "rating":
            if ans.answer_int is None:
                continue
            # The 1-to-5 scale, checked here rather than on the schema:
            # the column is shared with ``number``, whose range is its
            # own question's business.
            if not 1 <= ans.answer_int <= 5:
                raise HTTPException(status_code=400, detail=f"Question {q.id}: rating must be 1 to 5.")
            submitted[q.id] = {"answer_int": ans.answer_int}
        elif q.kind == "number":
            if ans.answer_int is None:
                continue
            if q.min_value is not None and ans.answer_int < q.min_value:
                raise HTTPException(status_code=400, detail=f"Question {q.id}: number below the lowest allowed.")
            if q.max_value is not None and ans.answer_int > q.max_value:
                raise HTTPException(status_code=400, detail=f"Question {q.id}: number above the highest allowed.")
            submitted[q.id] = {"answer_int": ans.answer_int}
        elif q.kind in ("text", "short_text"):
            text = (ans.answer_text or "").strip()
            if not text:
                continue
            submitted[q.id] = {"answer_text": text}
        elif q.kind == "single_choice":
            choices = ans.answer_choices or []
            if not choices:
                continue
            if len(choices) != 1:
                raise HTTPException(status_code=400, detail=f"Question {q.id} expects one choice.")
            if choices[0] not in q.options:
                raise HTTPException(status_code=400, detail=f"Question {q.id}: choice not in options.")
            submitted[q.id] = {"answer_choices": list(choices)}
        elif q.kind == "multi_choice":
            choices = ans.answer_choices or []
            if not choices:
                continue
            invalid = [c for c in choices if c not in q.options]
            if invalid:
                raise HTTPException(status_code=400, detail=f"Question {q.id}: choices not in options: {invalid}")
            # Drop duplicates while preserving order — multi-choice is a set.
            seen: set[str] = set()
            unique = [c for c in choices if not (c in seen or seen.add(c))]
            submitted[q.id] = {"answer_choices": unique}
        else:
            raise HTTPException(status_code=500, detail=f"Unknown question kind: {q.kind}")

    for q in questions:
        if q.required and q.id not in submitted:
            raise HTTPException(status_code=400, detail=f"Question {q.id} is required.")
    return submitted


def _write_responses(db: Session, form_id: str, submission_id: str, submitted: dict[str, dict[str, object]]) -> None:
    for qid, fields in submitted.items():
        db.add(
            FormResponse(
                form_id=form_id,
                question_id=qid,
                submission_id=submission_id,
                answer_int=fields.get("answer_int"),  # type: ignore[arg-type]
                answer_text=fields.get("answer_text"),  # type: ignore[arg-type]
                answer_choices=fields.get("answer_choices"),  # type: ignore[arg-type]
            )
        )


def _answers_for(db: Session, submission_id: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for r in db.query(FormResponse).filter(FormResponse.submission_id == submission_id).all():
        if r.answer_int is not None:
            out[r.question_id] = r.answer_int
        elif r.answer_text is not None:
            out[r.question_id] = r.answer_text
        elif r.answer_choices is not None:
            out[r.question_id] = list(r.answer_choices)
    return out


def _submission_by_token(db: Session, token: str) -> FormSubmission:
    """Resolve an edit-link token to its submission. 404 if the token
    doesn't match; 410 if the form is no longer public (archived)."""
    return public_access.resolve_by_token(
        db,
        FormSubmission,
        token,
        parent_model=Form,
        parent_fk=FormSubmission.form_id,
        gone_detail="This form is no longer available.",
    )


@router.post("/by-slug/{slug}/submit", response_model=FormSubmitAck, status_code=201)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def submit_form(
    request: Request,
    slug: str,
    data: FormSubmitIn,
    db: Session = Depends(get_db),
) -> FormSubmitAck:
    """Accept one public submission. Mints a secret edit-link token
    (raw returned once; only its hash stored) so the respondent can
    revisit and edit. Nothing in the response links the submission
    back to a person beyond the self-chosen pseudonym."""
    form = _resolve_form(db, slug)
    limits.assert_has_room_for_participant(db, form.tenant, "form", form.id)
    submitted = _build_submitted(_form_questions(db, form.id), data.answers)

    raw_token, token_hash = edit_token.new_edit_token()
    submission = FormSubmission(form_id=form.id, display_name=data.display_name, edit_token_hash=token_hash)
    db.add(submission)
    db.flush()  # need submission.id for the response rows
    _write_responses(db, form.id, submission.id, submitted)
    db.commit()
    logger.info("form_submitted", form_id=form.id, submission_id=submission.id)
    traffic.record("public_form", "submit")
    return FormSubmitAck(submission_id=submission.id, edit_token=raw_token)


@router.get("/by-token/{token}", response_model=FormEditOut)
def get_form_submission(token: str, db: Session = Depends(get_db)) -> FormEditOut:
    """Current values of a submission, for pre-filling the edit form.
    Gated by the secret token (the link)."""
    sub = _submission_by_token(db, token)
    return FormEditOut(
        display_name=sub.display_name,
        answers=_answers_for(db, sub.id),  # type: ignore[arg-type]
        link_recovered_at=sub.link_recovered_at,
    )


@router.put("/by-token/{token}", response_model=FormEditOut)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def update_form_submission(
    request: Request,
    token: str,
    data: FormSubmitIn,
    db: Session = Depends(get_db),
) -> FormEditOut:
    """Update a submission in place via its edit-link token. Replaces
    the submission's answer rows and the pseudonym."""
    sub = _submission_by_token(db, token)
    submitted = _build_submitted(_form_questions(db, sub.form_id), data.answers)
    db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
    sub.display_name = data.display_name
    _write_responses(db, sub.form_id, sub.id, submitted)
    db.commit()
    logger.info("form_submission_edited", form_id=sub.form_id, submission_id=sub.id)
    return FormEditOut(
        display_name=sub.display_name,
        answers=_answers_for(db, sub.id),  # type: ignore[arg-type]
        link_recovered_at=sub.link_recovered_at,
    )


@router.post("/by-token/{token}/withdraw", status_code=204)
@limiter.limit(Limits.PUBLIC_SUBMIT)
def withdraw_form_submission(request: Request, token: str, db: Session = Depends(get_db)) -> None:
    """Withdraw a submission via its edit-link token — the respondent
    deleting their own answers. Removes the response rows and the
    submission; nothing else references either (pseudonymous, no email)."""
    sub = _submission_by_token(db, token)
    form_id = sub.form_id
    db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
    db.delete(sub)
    db.commit()
    logger.info("form_submission_withdrawn", form_id=form_id)
