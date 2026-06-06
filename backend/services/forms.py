"""Forms-feature service helpers.

Three responsibilities:

* ``get_form_for_user`` — chapter-scoped fetch by id, mirroring
  ``access.get_event_for_user``. Same 404-on-out-of-scope rule.
* ``apply_questions`` — diff-applies a question payload against
  the form's current rows. Matches by id; new payload entries
  insert, matching ids update in place, ids on disk but absent
  from the payload delete (cascade takes their responses). The
  router calls this on both create (with empty current set) and
  update.
* ``question_aggregates`` — per-question summary for the details
  page. Pure SQL aggregation, no router fixtures needed.
"""

from typing import TYPE_CHECKING, Final

from fastapi import HTTPException
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ..models import Form, FormQuestion, FormResponse, User
from ..schemas.forms import FormQuestionSummary
from .access import chapter_ids_for_user

if TYPE_CHECKING:
    from ..schemas.forms import FormQuestionIn


# Mirror of the public ``QuestionKind`` literal — kept here so
# the service layer can validate without importing the schema
# module at runtime (avoids a circular dependency in the
# eventual frontend-typed import chain).
ALLOWED_KINDS: Final[frozenset[str]] = frozenset({"rating", "text", "short_text", "single_choice", "multi_choice"})
_CHOICE_KINDS: Final[frozenset[str]] = frozenset({"single_choice", "multi_choice"})


def get_form_by_slug_any(db: Session, slug: str) -> Form | None:
    """Slug lookup that includes archived forms — used by the
    public HTML route in ``routers/spa.py``. Returns ``None`` when
    the slug is unknown OR the form is archived: the public mini-
    app treats both as "no longer available", matching how the
    public JSON endpoint 410s on both. Mirrors how
    ``events_svc.get_event_by_slug_any`` is used by
    ``_serve_public_event`` (events choose to render archived
    events with a banner; forms don't have a meaningful "archived
    but viewable" mode, so a single null pathway is correct)."""
    form = db.query(Form).filter(Form.slug == slug).first()
    if form is None or form.archived_at is not None:
        return None
    return form


def get_form_for_user(db: Session, form_id: str, user: User) -> Form:
    """Fetch a form by id, scoped to the user's chapter set. 404
    if missing, in a chapter the user can't see, or the user has
    no live memberships. Mirrors ``access.get_event_for_user``."""
    ids = chapter_ids_for_user(db, user)
    if not ids:
        raise HTTPException(status_code=404, detail="Form not found")
    form = db.query(Form).filter(Form.id == form_id, Form.chapter_id.in_(ids)).first()
    if form is None:
        raise HTTPException(status_code=404, detail="Form not found")
    return form


def _validate_questions(questions: list["FormQuestionIn"]) -> None:
    """Per-kind sanity on a question payload. Raises HTTPException(400)
    — the router lets it propagate so the validation message
    surfaces verbatim."""
    for idx, q in enumerate(questions, start=1):
        if q.kind not in ALLOWED_KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"Question {idx}: unknown kind '{q.kind}'.",
            )
        if q.kind in _CHOICE_KINDS:
            cleaned = [opt.strip() for opt in q.options if opt.strip()]
            if len(cleaned) < 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {idx}: choice questions need at least two options.",
                )
            if len(set(cleaned)) != len(cleaned):
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {idx}: options must be unique.",
                )


def apply_questions(
    db: Session,
    form_id: str,
    questions: list["FormQuestionIn"],
) -> None:
    """Diff-apply a question payload against the form's current
    rows. Matches by id. Rows with no id (or an id not in the
    current set) are inserted; matching ids update in place;
    rows on disk but absent from the payload are deleted (the
    FK cascade takes their responses with them). Ordinals are
    re-numbered 1..N from input order.

    Caller commits the session."""
    _validate_questions(questions)

    existing = {q.id: q for q in db.query(FormQuestion).filter(FormQuestion.form_id == form_id).all()}
    seen_ids: set[str] = set()
    for ordinal, payload in enumerate(questions, start=1):
        # Kind-aware field normalisation. Non-choice kinds get an
        # empty options list regardless of what the client sent;
        # non-rating kinds drop the scale labels. Keeps the stored
        # row tidy and makes the public form's render kind-driven
        # without per-kind defensive checks.
        clean_options = [opt.strip() for opt in payload.options if opt.strip()] if payload.kind in _CHOICE_KINDS else []
        low_label = payload.low_label if payload.kind == "rating" else None
        high_label = payload.high_label if payload.kind == "rating" else None

        if payload.id and payload.id in existing:
            row = existing[payload.id]
            row.ordinal = ordinal
            row.kind = payload.kind
            row.prompt = payload.prompt.strip()
            row.required = payload.required
            row.options = clean_options
            row.low_label = low_label
            row.high_label = high_label
            seen_ids.add(payload.id)
        else:
            # Insert. An id submitted that doesn't exist on disk is
            # ignored — we always mint a fresh uuid for new rows so
            # a client guessing at ids can't collide with another
            # form's question.
            db.add(
                FormQuestion(
                    form_id=form_id,
                    ordinal=ordinal,
                    kind=payload.kind,
                    prompt=payload.prompt.strip(),
                    required=payload.required,
                    options=clean_options,
                    low_label=low_label,
                    high_label=high_label,
                )
            )

    for qid, row in existing.items():
        if qid not in seen_ids:
            db.delete(row)
    db.flush()


def submission_count(db: Session, form_id: str) -> int:
    """Distinct submission ids for the form."""
    return (
        db.query(func.count(distinct(FormResponse.submission_id))).filter(FormResponse.form_id == form_id).scalar() or 0
    )


def question_aggregates(db: Session, form_id: str) -> list[FormQuestionSummary]:
    """One ``FormQuestionSummary`` per question, ordinal-ordered.
    Per-kind shape:

    * ``rating`` — 5-bucket distribution + average.
    * ``text`` / ``short_text`` — raw answers, newest first.
    * ``single_choice`` / ``multi_choice`` — option → count map.
    """
    questions = db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()
    summaries: list[FormQuestionSummary] = []
    for q in questions:
        if q.kind == "rating":
            rows = (
                db.query(FormResponse.answer_int, func.count(FormResponse.id))
                .filter(
                    FormResponse.form_id == form_id,
                    FormResponse.question_id == q.id,
                    FormResponse.answer_int.is_not(None),
                )
                .group_by(FormResponse.answer_int)
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
                FormQuestionSummary(
                    id=q.id,
                    ordinal=q.ordinal,
                    kind=q.kind,
                    prompt=q.prompt,
                    response_count=total,
                    rating_distribution=distribution,
                    rating_average=avg,
                )
            )
        elif q.kind in ("text", "short_text"):
            texts = (
                db.query(FormResponse.answer_text)
                .filter(
                    FormResponse.form_id == form_id,
                    FormResponse.question_id == q.id,
                    FormResponse.answer_text.is_not(None),
                )
                .order_by(FormResponse.created_at.desc())
                .all()
            )
            summaries.append(
                FormQuestionSummary(
                    id=q.id,
                    ordinal=q.ordinal,
                    kind=q.kind,
                    prompt=q.prompt,
                    response_count=len(texts),
                    texts=[t[0] for t in texts],
                )
            )
        elif q.kind in _CHOICE_KINDS:
            counts: dict[str, int] = {opt: 0 for opt in q.options}
            rows = (
                db.query(FormResponse.answer_choices)
                .filter(
                    FormResponse.form_id == form_id,
                    FormResponse.question_id == q.id,
                    FormResponse.answer_choices.is_not(None),
                )
                .all()
            )
            response_count = 0
            for (choices,) in rows:
                if not choices:
                    continue
                response_count += 1
                for c in choices:
                    if c in counts:
                        counts[c] += 1
            summaries.append(
                FormQuestionSummary(
                    id=q.id,
                    ordinal=q.ordinal,
                    kind=q.kind,
                    prompt=q.prompt,
                    response_count=response_count,
                    choice_counts=counts,
                )
            )
        else:
            # Unknown kind — shouldn't reach prod (the kind is
            # validated on write) but the summary endpoint shouldn't
            # crash on a row from a malformed migration.
            summaries.append(
                FormQuestionSummary(
                    id=q.id,
                    ordinal=q.ordinal,
                    kind=q.kind,
                    prompt=q.prompt,
                    response_count=0,
                )
            )
    return summaries


def to_out(db: Session, form: Form) -> dict[str, object]:
    """Build the dict payload for ``FormOut.model_validate``. Loads
    the chapter name (one lookup) and the question list (one
    query) — both are required for the organiser-facing DTO."""
    from ..models import Chapter

    chapter_name: str | None = None
    if form.chapter_id is not None:
        row = db.query(Chapter.name).filter(Chapter.id == form.chapter_id, Chapter.deleted_at.is_(None)).first()
        chapter_name = row[0] if row else None

    questions = db.query(FormQuestion).filter(FormQuestion.form_id == form.id).order_by(FormQuestion.ordinal).all()

    return {
        "id": form.id,
        "slug": form.slug,
        "name": form.name,
        "locale": form.locale,
        "chapter_id": form.chapter_id,
        "chapter_name": chapter_name,
        "archived": form.archived_at is not None,
        "created_at": form.created_at,
        "questions": [
            {
                "id": q.id,
                "ordinal": q.ordinal,
                "kind": q.kind,
                "prompt": q.prompt,
                "required": q.required,
                "options": q.options,
                "low_label": q.low_label,
                "high_label": q.high_label,
            }
            for q in questions
        ],
    }
