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

import io
import secrets
from functools import lru_cache

import qrcode
import qrcode.image.svg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Form, FormQuestion, FormResponse
from ..schemas.forms import (
    FormQuestionOut,
    FormSubmitAck,
    FormSubmitIn,
    PublicFormOut,
)
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
    form = db.query(Form).filter(Form.slug == slug).first()
    if form is None or form.archived_at is not None:
        raise HTTPException(status_code=410, detail="This form is no longer available.")
    return form


def _form_questions(db: Session, form_id: str) -> list[FormQuestion]:
    return db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()


@lru_cache(maxsize=256)
def _render_qr(slug: str) -> bytes:
    """Generate the QR SVG for one form slug. Same shape as the
    events QR helper: SVG-path rendering is pure-Python (no PIL),
    transparent background, per-process LRU caches repeat fetches."""
    target = f"{PUBLIC_BASE_URL}/f/{slug}"
    qr = qrcode.QRCode(box_size=10, border=2, image_factory=qrcode.image.svg.SvgPathImage)
    qr.add_data(target)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image().save(buf)
    return buf.getvalue()


@router.get("/by-slug/{slug}/qr.svg")
def get_form_qr(slug: str, db: Session = Depends(get_db)) -> Response:
    """QR SVG for one slug. Resolves the form first so a typo'd
    slug 410s rather than 200ing with a wrong-target QR."""
    form = _resolve_form(db, slug)
    return Response(
        content=_render_qr(form.slug),
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/by-slug/{slug}", response_model=PublicFormOut)
def get_public_form(slug: str, db: Session = Depends(get_db)) -> PublicFormOut:
    form = _resolve_form(db, slug)
    questions = _form_questions(db, form.id)
    return PublicFormOut(
        id=form.id,
        name=form.name,
        locale=form.locale,
        questions=[FormQuestionOut.model_validate(q) for q in questions],
    )


@router.post("/by-slug/{slug}/submit", response_model=FormSubmitAck, status_code=201)
@limiter.limit(Limits.PUBLIC_FEEDBACK)
def submit_form(
    request: Request,
    slug: str,
    data: FormSubmitIn,
    db: Session = Depends(get_db),
) -> FormSubmitAck:
    """Accept one public submission. Validates each answer
    against its question's stored kind. Skipped optional
    questions are simply absent from the stored rows; skipped
    required questions 400.

    Returns the random ``submission_id`` so the client can
    confirm the submit landed. Nothing in the response links the
    submission back to the submitter — same privacy contract as
    the post-event feedback flow."""
    form = _resolve_form(db, slug)
    questions = _form_questions(db, form.id)
    by_id = {q.id: q for q in questions}

    submitted: dict[str, dict[str, object]] = {}
    for ans in data.answers:
        q = by_id.get(ans.question_id)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        if q.kind == "rating":
            if ans.answer_int is None:
                continue
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
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {q.id} expects one choice.",
                )
            if choices[0] not in q.options:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {q.id}: choice not in options.",
                )
            submitted[q.id] = {"answer_choices": list(choices)}
        elif q.kind == "multi_choice":
            choices = ans.answer_choices or []
            if not choices:
                continue
            invalid = [c for c in choices if c not in q.options]
            if invalid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {q.id}: choices not in options: {invalid}",
                )
            # Drop duplicates while preserving order — multi-choice
            # is a set semantically.
            seen: set[str] = set()
            unique = [c for c in choices if not (c in seen or seen.add(c))]
            submitted[q.id] = {"answer_choices": unique}
        else:
            raise HTTPException(status_code=500, detail=f"Unknown question kind: {q.kind}")

    for q in questions:
        if q.required and q.id not in submitted:
            raise HTTPException(status_code=400, detail=f"Question {q.id} is required.")

    submission_id = secrets.token_urlsafe(16)
    for qid, fields in submitted.items():
        db.add(
            FormResponse(
                form_id=form.id,
                question_id=qid,
                submission_id=submission_id,
                answer_int=fields.get("answer_int"),  # type: ignore[arg-type]
                answer_text=fields.get("answer_text"),  # type: ignore[arg-type]
                answer_choices=fields.get("answer_choices"),  # type: ignore[arg-type]
            )
        )

    db.commit()
    logger.info("form_submitted", form_id=form.id, submission_id=submission_id)
    return FormSubmitAck(submission_id=submission_id)
