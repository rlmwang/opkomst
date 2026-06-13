"""Forms-feature service helpers.

Responsibilities:

* ``apply_questions`` — diff-applies a question payload against
  the form's current rows. Matches by id; new payload entries
  insert, matching ids update in place, ids on disk but absent
  from the payload delete (cascade takes their responses). The
  router calls this on both create (with empty current set) and
  update.
* ``enrich`` / ``to_out`` / ``to_public_out`` — the three DTO
  projections (batched list rows, single organiser form, public
  by-slug form).
* ``question_aggregates`` / ``submission_count`` / ``submissions``
  — organiser-side reads for the details page + CSV export. Pure
  SQL aggregation, no router fixture needed.

Chapter-scoped lookups live in ``services.access`` (``get_form_for_user``,
``form_scope_filter``) alongside the event equivalents.
"""

from typing import TYPE_CHECKING, Final, get_args

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Form, FormQuestion, FormResponse, FormSubmission
from ..schemas.forms import (
    FormListOut,
    FormOut,
    FormQuestionOut,
    FormQuestionSummary,
    FormSubmissionOut,
    PublicFormOut,
    QuestionKind,
)
from .ratings import rating_distribution

if TYPE_CHECKING:
    from ..schemas.forms import FormQuestionIn


# Single source of truth for the supported kinds: the public
# ``QuestionKind`` literal. ``_CHOICE_KINDS`` is the subset that
# carries an options list.
ALLOWED_KINDS: Final[frozenset[str]] = frozenset(get_args(QuestionKind))
_CHOICE_KINDS: Final[frozenset[str]] = frozenset({"single_choice", "multi_choice"})


def get_form_by_slug_any(db: Session, slug: str) -> Form | None:
    """Slug lookup that includes archived forms — used by the
    public HTML route in ``routers/spa.py``. Returns ``None`` when
    the slug is unknown OR the form is archived: the public mini-
    app treats both as "no longer available", matching how the
    public JSON endpoint 410s on both."""
    form = db.query(Form).filter(Form.slug == slug).first()
    if form is None or form.archived_at is not None:
        return None
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


# --- DTO projections -------------------------------------------------


def _chapter_names(db: Session, chapter_ids: set[str]) -> dict[str, str]:
    """Live chapter id → name, batched. Soft-deleted chapters drop
    out (the name is then ``None`` at the call site)."""
    if not chapter_ids:
        return {}
    rows = db.query(Chapter.id, Chapter.name).filter(Chapter.id.in_(chapter_ids), Chapter.deleted_at.is_(None)).all()
    return {cid: name for cid, name in rows}


def enrich(db: Session, forms: list[Form]) -> list[FormListOut]:
    """Build ``FormListOut`` rows with a single batched chapter-name
    lookup, regardless of how many forms. The list views never
    render questions, so this projection doesn't load them."""
    if not forms:
        return []
    names = _chapter_names(db, {f.chapter_id for f in forms if f.chapter_id})
    return [
        FormListOut(
            id=f.id,
            slug=f.slug,
            name=f.name,
            locale=f.locale,
            chapter_id=f.chapter_id,
            chapter_name=names.get(f.chapter_id) if f.chapter_id else None,
            archived=f.archived_at is not None,
            created_at=f.created_at,
        )
        for f in forms
    ]


def _questions(db: Session, form_id: str) -> list[FormQuestion]:
    return db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()


def to_out(db: Session, form: Form) -> FormOut:
    """Single-form organiser DTO: the list-row fields plus the full
    question list. One chapter-name lookup + one question query."""
    chapter_name = _chapter_names(db, {form.chapter_id}).get(form.chapter_id) if form.chapter_id else None
    return FormOut(
        id=form.id,
        slug=form.slug,
        name=form.name,
        locale=form.locale,
        chapter_id=form.chapter_id,
        chapter_name=chapter_name,
        archived=form.archived_at is not None,
        created_at=form.created_at,
        description=form.description,
        questions=[FormQuestionOut.model_validate(q) for q in _questions(db, form.id)],
    )


def to_public_out(db: Session, form: Form) -> PublicFormOut:
    """Public by-slug DTO: name + description + locale + questions in
    display order, nothing internal. Used by the public JSON endpoint
    and the server-rendered mini-app shell."""
    return PublicFormOut(
        id=form.id,
        name=form.name,
        description=form.description,
        locale=form.locale,
        questions=[FormQuestionOut.model_validate(q) for q in _questions(db, form.id)],
    )


# --- Organiser-side reads --------------------------------------------


def submission_count(db: Session, form_id: str) -> int:
    """Number of fill-outs (parent submission rows) for the form."""
    return db.query(func.count(FormSubmission.id)).filter(FormSubmission.form_id == form_id).scalar() or 0


def question_aggregates(db: Session, form_id: str) -> list[FormQuestionSummary]:
    """One ``FormQuestionSummary`` per question, ordinal-ordered.
    Per-kind shape:

    * ``rating`` — 5-bucket distribution + average.
    * ``text`` / ``short_text`` — raw answers, newest first.
    * ``single_choice`` / ``multi_choice`` — option → count map.
    """
    summaries: list[FormQuestionSummary] = []
    for q in _questions(db, form_id):
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
            distribution, total, average = rating_distribution([(v, c) for v, c in rows])
            summaries.append(
                FormQuestionSummary(
                    id=q.id,
                    ordinal=q.ordinal,
                    kind=q.kind,
                    prompt=q.prompt,
                    response_count=total,
                    rating_distribution=distribution,
                    rating_average=average,
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
            # Unknown kind — unreachable in practice (validated on
            # write + DB CHECK), but the summary endpoint shouldn't
            # crash on a malformed row.
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


def submissions(db: Session, form_id: str) -> list[FormSubmissionOut]:
    """Per-submission rows for the CSV export, keyed by question id.
    One ``FormSubmissionOut`` per fill-out, carrying the pseudonym
    (``display_name``, NULL = anonymous); the answer value matches the
    question kind (int / str / list[str]).

    Privacy: the submission id is opaque and the only respondent
    identifier is the self-chosen pseudonym."""
    kinds = {q.id: q.kind for q in _questions(db, form_id)}
    subs = db.query(FormSubmission).filter(FormSubmission.form_id == form_id).order_by(FormSubmission.created_at).all()
    if not subs:
        return []
    sub_ids = [s.id for s in subs]
    answers: dict[str, dict[str, int | str | list[str]]] = {sid: {} for sid in sub_ids}
    for r in db.query(FormResponse).filter(FormResponse.submission_id.in_(sub_ids)).all():
        kind = kinds.get(r.question_id)
        if kind is None:
            continue
        if kind == "rating" and r.answer_int is not None:
            answers[r.submission_id][r.question_id] = r.answer_int
        elif kind in ("text", "short_text") and r.answer_text is not None:
            answers[r.submission_id][r.question_id] = r.answer_text
        elif kind in _CHOICE_KINDS and r.answer_choices is not None:
            answers[r.submission_id][r.question_id] = list(r.answer_choices)

    return [
        FormSubmissionOut(
            submission_id=s.id,
            display_name=s.display_name,
            created_at=s.created_at,
            answers=answers[s.id],
        )
        for s in subs
    ]
