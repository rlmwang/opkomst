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

* ``query`` — the only place the ``forms`` table is read from. Every
  read names the mode it means, because the table holds both products
  (``docs/design-quizzes.md``) and a read that forgets puts quizzes in
  the forms list. ``tests/test_form_modes.py`` greps the tree for
  anyone querying it anywhere else.

Chapter-scoped lookups live in ``services.access`` (``get_form_for_user``,
``form_scope_filter``) alongside the event equivalents; they take the
mode for the same reason.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast, get_args

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from ..models import Chapter, CompassAxis, Form, FormQuestion, FormResponse, FormSubmission
from ..schemas.forms import (
    CompassAxisOut,
    CompassAxisSummary,
    CompassPoint,
    CompassSummary,
    FormListOut,
    FormMode,
    FormOut,
    FormQuestionOut,
    FormQuestionSummary,
    FormSubmissionOut,
    PublicFormOut,
    PublicQuestionOut,
    QuestionKind,
    QuizSubmissionOut,
)
from . import archive as archive_svc
from . import compass, numbers, public_access, quizzes, tenancy
from . import image as image_svc
from .ratings import rating_distribution

if TYPE_CHECKING:
    from ..schemas.forms import CompassAxisIn, FormQuestionIn


# Single source of truth for the supported kinds: the public
# ``QuestionKind`` literal. ``_CHOICE_KINDS`` is the subset that
# carries an options list.
ALLOWED_KINDS: Final[frozenset[str]] = frozenset(get_args(QuestionKind))
_CHOICE_KINDS: Final[frozenset[str]] = frozenset({"single_choice", "multi_choice"})
_TEXT_KINDS: Final[frozenset[str]] = frozenset({"text", "short_text"})


def as_mode(value: str) -> FormMode:
    """The column is text and the DTO is the two-value vocabulary. The
    CHECK constraint on ``forms.mode`` is what makes this narrowing
    true, which is why it is a cast rather than a parse."""
    return cast(FormMode, value)


def query(db: Session, mode: str) -> Query[Form]:
    """Every read of the ``forms`` table starts here.

    The table carries both products, so a query without the mode
    predicate is a quiz in somebody's questionnaire list, or the other
    way round. Making that one function rather than one convention is
    what lets a test check it: ``tests/test_form_modes.py`` fails on a
    ``db.query(Form)`` anywhere else in the tree."""
    return db.query(Form).filter(Form.mode == mode)


def get_form_by_slug_any(db: Session, slug: str, mode: str) -> Form | None:
    """Slug lookup that includes archived forms — used by the
    public HTML route in ``routers/spa.py``. Returns ``None`` when
    the slug is unknown OR the form is archived: the public mini-
    app treats both as "no longer available", matching how the
    public JSON endpoint 410s on both."""
    form = query(db, mode).filter(Form.slug == slug).first()
    if form is None or form.archived_at is not None:
        return None
    tenancy.bind(form.tenant_id, form.tenant.brand_slug)
    return form


def resolve_public(db: Session, slug: str, mode: str) -> Form:
    """The public JSON surface's lookup: a live form of this mode, or
    410. Unknown, archived and "that is the other product's slug" are
    one answer on purpose, the same way an unknown slug and an archived
    one already were."""
    return public_access.resolve_by_slug(
        db,
        Form,
        slug,
        gone_detail="This form is no longer available.",
        where=Form.mode == mode,
    )


def _validate_questions(questions: list["FormQuestionIn"], mode: str, axes: list["CompassAxisIn"]) -> None:
    """Per-kind sanity on a question payload. Raises HTTPException(400)
    — the router lets it propagate so the validation message
    surfaces verbatim."""
    # A questionnaire with nothing to answer is not a draft, it is a
    # public page whose only button does nothing. All three products
    # need at least one question to be a thing at all, so the save that
    # would leave none is refused rather than published.
    if not questions:
        raise HTTPException(status_code=400, detail="Add at least one question before saving.")
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
        if q.kind == "number":
            if q.min_value is not None and q.max_value is not None and q.min_value > q.max_value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {idx}: the lowest allowed number is above the highest.",
                )
            # A step the bounds cannot reach is a question nobody can
            # answer: 0 to 10 in steps of 7 accepts 0 and 7 and nothing
            # else, which is fine, but 3 to 5 in steps of 7 accepts
            # nothing at all.
            if q.step and q.min_value is not None and q.max_value is not None:
                first = q.min_value
                if first + (q.step - (first % q.step)) % q.step > q.max_value and first % q.step != 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Question {idx}: no number between the lowest and the highest lands on this step.",
                    )
    if mode == "quiz":
        # Both checked when the organiser saves, not when somebody
        # submits: at submit time the person who can fix it is not the
        # person looking at the screen.
        quizzes.validate_kinds(questions)
        quizzes.validate_keys(questions)
    if mode == "compass":
        # A draft kompas with neither questions nor axes is a thing an
        # organiser saves and comes back to. The moment it has either,
        # the axes have to be nameable: a question pointing at an
        # unnamed side is a result screen with a hole in the sentence.
        if questions or axes:
            compass.validate_axes(axes)
        if questions:
            compass.validate_questions(questions, axes)


def apply_axes(db: Session, form_id: str, axes: list["CompassAxisIn"]) -> None:
    """Diff-apply a kompas's two axes. Matched by ``axis`` rather than
    by id, because there are exactly two of them and which is which is
    the whole of their identity: an organiser cannot add a third or
    delete one, only rename what is there.

    Caller commits the session."""
    existing = {a.axis: a for a in db.query(CompassAxis).filter(CompassAxis.form_id == form_id).all()}
    for payload in axes:
        row = existing.pop(payload.axis, None)
        fields = {
            "name": payload.name.strip(),
            "description": (payload.description or "").strip() or None,
            "low_name": payload.low_name.strip(),
            "high_name": payload.high_name.strip(),
        }
        if row is None:
            db.add(CompassAxis(form_id=form_id, axis=payload.axis, **fields))
        else:
            for key, value in fields.items():
                setattr(row, key, value)
    # An axis on disk the payload did not name. Only reachable by
    # switching a form's mode, which nothing does, so deleting is the
    # honest handling of a row that no longer belongs to anything.
    for row in existing.values():
        db.delete(row)
    db.flush()


def apply_questions(
    db: Session,
    form_id: str,
    questions: list["FormQuestionIn"],
    mode: str,
    axes: list["CompassAxisIn"] | None = None,
) -> None:
    """Diff-apply a question payload against the form's current
    rows. Matches by id. Rows with no id (or an id not in the
    current set) are inserted; matching ids update in place;
    rows on disk but absent from the payload are deleted (the
    FK cascade takes their responses with them). Ordinals are
    re-numbered 1..N from input order.

    ``axes`` is the kompas's axis payload, which the question
    validation needs: a question's direction points at one of them, so
    the two are only checkable together (``services/compass``).

    Caller commits the session."""
    _validate_questions(questions, mode, list(axes or []))

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
        is_number = payload.kind == "number"
        min_value = payload.min_value if is_number else None
        max_value = payload.max_value if is_number else None
        step = payload.step if is_number else None
        # The answer key, on the same terms: a survey has none.
        scored = mode == "quiz"
        # One point unless the organiser said a number. Zero stays
        # expressible, it just has to be typed.
        points = (payload.points if payload.points is not None else 1) if scored else 0
        # Every quiz question is answered. Skipping one is a free zero
        # rather than a choice, and the walk gates on this
        # (``public_quiz``), so it is the server that decides it and not
        # the editor that happens not to offer the switch.
        required = True if mode == "quiz" else payload.required
        correct_int = payload.correct_int if scored and payload.kind in ("rating", "number") else None
        correct_text = None
        correct_choices = (
            [c.strip() for c in (payload.correct_choices or []) if c.strip()]
            if scored and payload.kind in _CHOICE_KINDS
            else None
        )
        tolerance = payload.tolerance if scored and payload.kind == "number" else None
        # The direction, on the same terms: only a kompas has one, and
        # only on the half of the question its kind puts it on.
        pointed = mode == "compass"
        pole = payload.pole if pointed and payload.kind == "rating" else None
        option_poles = (
            [p for p, opt in zip(payload.option_poles or [], payload.options, strict=False) if opt.strip()]
            if pointed and payload.kind == "single_choice"
            else None
        )

        if payload.id and payload.id in existing:
            row = existing[payload.id]
            row.ordinal = ordinal
            row.kind = payload.kind
            row.prompt = payload.prompt.strip()
            row.required = required
            row.options = clean_options
            row.low_label = low_label
            row.high_label = high_label
            row.min_value = min_value
            row.max_value = max_value
            row.step = step
            row.points = points
            row.correct_int = correct_int
            row.correct_text = correct_text
            row.correct_choices = correct_choices
            row.tolerance = tolerance
            row.pole = pole
            row.option_poles = option_poles
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
                    required=required,
                    options=clean_options,
                    low_label=low_label,
                    high_label=high_label,
                    min_value=min_value,
                    max_value=max_value,
                    step=step,
                    points=points,
                    correct_int=correct_int,
                    correct_text=correct_text,
                    correct_choices=correct_choices,
                    tolerance=tolerance,
                    pole=pole,
                    option_poles=option_poles,
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


def _submission_counts(db: Session, form_ids: list[str]) -> dict[str, int]:
    """Per-form submission counts via one grouped query (no N+1)."""
    return {
        fid: int(n)
        for fid, n in db.query(FormSubmission.form_id, func.count(FormSubmission.id))
        .filter(FormSubmission.form_id.in_(form_ids))
        .group_by(FormSubmission.form_id)
        .all()
    }


def enrich(db: Session, forms: list[Form]) -> list[FormListOut]:
    """Build ``FormListOut`` rows with batched lookups: one chapter-name
    lookup + one grouped submission-count query, regardless of how many
    forms. The list views never render questions, so this projection
    doesn't load them."""
    if not forms:
        return []
    names = _chapter_names(db, {f.chapter_id for f in forms if f.chapter_id})
    counts = _submission_counts(db, [f.id for f in forms])
    return [
        FormListOut(
            id=f.id,
            slug=f.slug,
            mode=as_mode(f.mode),
            name_nl=f.name_nl,
            name_en=f.name_en,
            locale=f.locale,
            chapter_id=f.chapter_id,
            chapter_name=names.get(f.chapter_id) if f.chapter_id else None,
            archived=f.archived_at is not None,
            created_at=f.created_at,
            submission_count=counts.get(f.id, 0),
        )
        for f in forms
    ]


def archived_enrich(db: Session, rows: list[Mapping[str, Any]]) -> list[FormListOut]:
    """The same DTO for forms that have left the live tables: columns
    from the twin, submission counts from the archived submissions."""
    if not rows:
        return []
    names = _chapter_names(db, {r["chapter_id"] for r in rows if r["chapter_id"]})
    counts = archive_svc.child_counts(db, "form_submissions", "form_id", [r["id"] for r in rows])
    return [
        FormListOut(
            id=r["id"],
            slug=r["slug"],
            mode=as_mode(r["mode"]),
            name_nl=r["name_nl"],
            name_en=r["name_en"],
            locale=r["locale"],
            chapter_id=r["chapter_id"],
            chapter_name=names.get(r["chapter_id"]) if r["chapter_id"] else None,
            archived=True,
            created_at=r["created_at"],
            submission_count=counts.get(r["id"], 0),
        )
        for r in rows
    ]


def _axes_out(db: Session, form: Form) -> list[CompassAxisOut]:
    """The two axis rows, ``x`` first. Empty on the two products that
    place nobody, which is one query they pay for and the shape every
    caller already handles."""
    if form.mode != "compass":
        return []
    return [CompassAxisOut.model_validate(a) for a in compass.axes_of(db, form.id)]


def _questions(db: Session, form_id: str) -> list[FormQuestion]:
    return db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()


def questions_of(db: Session, form_id: str) -> list[FormQuestion]:
    """The question rows, for a caller that has to mark answers against
    them (``routers/form`` asking ``services/quiz`` for the score
    stats)."""
    return _questions(db, form_id)


def to_out(db: Session, form: Form) -> FormOut:
    """Single-form organiser DTO: the list-row fields plus the full
    question list. One chapter-name lookup + one question query."""
    chapter_name = _chapter_names(db, {form.chapter_id}).get(form.chapter_id) if form.chapter_id else None
    return FormOut(
        id=form.id,
        slug=form.slug,
        mode=as_mode(form.mode),
        name_nl=form.name_nl,
        name_en=form.name_en,
        locale=form.locale,
        chapter_id=form.chapter_id,
        chapter_name=chapter_name,
        archived=form.archived_at is not None,
        created_at=form.created_at,
        submission_count=submission_count(db, form.id),
        description_nl=form.description_nl,
        description_en=form.description_en,
        image_url=image_svc.public_url(form.image_path),
        image_artist_instagram=form.image_artist_instagram,
        reveal_answers=form.reveal_answers,
        answers_editable=form.answers_editable,
        name_required=form.name_required,
        axes=_axes_out(db, form),
        questions=[FormQuestionOut.model_validate(q) for q in _questions(db, form.id)],
    )


def to_public_out(db: Session, form: Form) -> PublicFormOut:
    """Public by-slug DTO: name + description + locale + questions in
    display order, nothing internal. Used by the public JSON endpoint
    and the server-rendered mini-app shell."""
    return PublicFormOut(
        id=form.id,
        name_nl=form.name_nl,
        name_en=form.name_en,
        description_nl=form.description_nl,
        description_en=form.description_en,
        image_url=image_svc.public_url(form.image_path),
        image_artist_instagram=form.image_artist_instagram,
        locale=form.locale,
        mode=as_mode(form.mode),
        name_required=form.name_required,
        answers_editable=form.answers_editable,
        # What the kompas places you on. Not a secret, and the cover
        # page names it before anybody answers; which answer points
        # where is the part that waits for the result.
        axes=_axes_out(db, form),
        # ``PublicQuestionOut``, not ``FormQuestionOut``: this is the
        # shape that leaves out the answer key, and it is the only thing
        # standing between a quiz and being solved by view-source.
        questions=[PublicQuestionOut.model_validate(q) for q in _questions(db, form.id)],
    )


# --- Organiser-side reads --------------------------------------------


def submission_count(db: Session, form_id: str) -> int:
    """Number of fill-outs (parent submission rows) for the form."""
    return db.query(func.count(FormSubmission.id)).filter(FormSubmission.form_id == form_id).scalar() or 0


def _summary(q: FormQuestion, correct_share: float | None, **fields: object) -> FormQuestionSummary:
    """One aggregate row, plus the one number only a quiz has."""
    return FormQuestionSummary(
        id=q.id,
        ordinal=q.ordinal,
        kind=q.kind,
        prompt=q.prompt,
        correct_share=correct_share,
        # Which way this question pushed. The organiser's page reads a
        # count next to the direction that earned it, which is the
        # difference between "34 picked Rotterdam" and "34 moved
        # toward Rechts" (``docs/design-kompas.md`` 4.5).
        pole=q.pole,
        option_poles=list(q.option_poles) if q.option_poles else None,
        **fields,  # type: ignore[arg-type]
    )


def _numeric_counts(db: Session, form_id: str, question_ids: list[str]) -> dict[str, list[tuple[int, int]]]:
    """``question_id -> [(answer, times given)]`` for every rating and
    number question at once. The database does the counting; a rating
    reads the pairs as its distribution and a number expands them back
    into values."""
    if not question_ids:
        return {}
    out: dict[str, list[tuple[int, int]]] = {}
    for qid, value, n in (
        db.query(FormResponse.question_id, FormResponse.answer_int, func.count(FormResponse.id))
        .filter(
            FormResponse.form_id == form_id,
            FormResponse.question_id.in_(question_ids),
            FormResponse.answer_int.is_not(None),
        )
        .group_by(FormResponse.question_id, FormResponse.answer_int)
        .all()
    ):
        out.setdefault(qid, []).append((value, n))
    return out


def _texts(db: Session, form_id: str, question_ids: list[str]) -> dict[str, list[str]]:
    """``question_id -> answers, newest first`` for every open question
    at once."""
    if not question_ids:
        return {}
    out: dict[str, list[str]] = {}
    for qid, text in (
        db.query(FormResponse.question_id, FormResponse.answer_text)
        .filter(
            FormResponse.form_id == form_id,
            FormResponse.question_id.in_(question_ids),
            FormResponse.answer_text.is_not(None),
        )
        .order_by(FormResponse.created_at.desc())
        .all()
    ):
        out.setdefault(qid, []).append(text)
    return out


def _chosen(db: Session, form_id: str, question_ids: list[str]) -> dict[str, list[list[str]]]:
    """``question_id -> one list per answer`` for every choice question
    at once. The ticks live in an array column, so the tally is folded
    here rather than grouped in SQL."""
    if not question_ids:
        return {}
    out: dict[str, list[list[str]]] = {}
    for qid, choices in (
        db.query(FormResponse.question_id, FormResponse.answer_choices)
        .filter(
            FormResponse.form_id == form_id,
            FormResponse.question_id.in_(question_ids),
            FormResponse.answer_choices.is_not(None),
        )
        .all()
    ):
        if choices:
            out.setdefault(qid, []).append(list(choices))
    return out


def question_aggregates(db: Session, form_id: str, questions: list[FormQuestion]) -> list[FormQuestionSummary]:
    """One ``FormQuestionSummary`` per question, ordinal-ordered.
    Per-kind shape:

    * ``rating`` — 5-bucket distribution + average.
    * ``number`` — average, lowest, highest.
    * ``text`` / ``short_text`` — raw answers, newest first.
    * ``single_choice`` / ``multi_choice`` — option → count map.

    Batched by kind, not by question: four queries for the whole page
    however many questions it has, because a form with thirty of them
    is exactly the form whose results page is worth loading fast.
    """
    if not questions:
        return []

    numeric = _numeric_counts(db, form_id, [q.id for q in questions if q.kind in ("rating", "number")])
    texts = _texts(db, form_id, [q.id for q in questions if q.kind in _TEXT_KINDS])
    chosen = _chosen(db, form_id, [q.id for q in questions if q.kind in _CHOICE_KINDS])
    shares = quizzes.correct_shares(db, form_id, questions)

    summaries: list[FormQuestionSummary] = []
    for q in questions:
        share = shares.get(q.id)
        if q.kind == "rating":
            distribution, total, average = rating_distribution(numeric.get(q.id, []))
            summaries.append(
                _summary(
                    q,
                    share,
                    response_count=total,
                    rating_distribution=distribution,
                    rating_average=average,
                )
            )
        elif q.kind == "number":
            # Back to one entry per answer: the average, the extremes and
            # the histogram are all about the values as given.
            values = [value for value, n in numeric.get(q.id, []) for _ in range(n)]
            summaries.append(
                _summary(
                    q,
                    share,
                    response_count=len(values),
                    number_average=round(sum(values) / len(values), 1) if values else None,
                    number_min=min(values) if values else None,
                    number_max=max(values) if values else None,
                    number_buckets=numbers.histogram(values, q.min_value, q.max_value, q.step) or None,
                )
            )
        elif q.kind in _TEXT_KINDS:
            answers = texts.get(q.id, [])
            summaries.append(_summary(q, share, response_count=len(answers), texts=answers))
        elif q.kind in _CHOICE_KINDS:
            counts: dict[str, int] = {opt: 0 for opt in q.options}
            answers_given = chosen.get(q.id, [])
            for choices in answers_given:
                for c in choices:
                    if c in counts:
                        counts[c] += 1
            summaries.append(
                _summary(
                    q,
                    share,
                    response_count=len(answers_given),
                    choice_counts=counts,
                )
            )
        else:
            # Unknown kind — unreachable in practice (validated on
            # write + DB CHECK), but the summary endpoint shouldn't
            # crash on a malformed row.
            summaries.append(_summary(q, share, response_count=0))
    return summaries


def compass_places(db: Session, form: Form, questions: list[FormQuestion]) -> dict[str, compass.Position]:
    """Where every submission sits, read once for a whole page.

    Both halves of a kompas page (the axes and the dots) place the same
    people from the same answers. Reading it here and handing it to both
    is what keeps one page from loading every answer twice."""
    return compass.positions(db, questions, form.id)


def compass_points(
    db: Session,
    form: Form,
    places: dict[str, compass.Position],
    *,
    you: str | None = None,
) -> list[CompassPoint]:
    """Every submission as a dot, in submission order.

    ``you`` marks one of them as the reader's own; the organiser's copy
    passes nothing, because on their page nobody is "you". The name is
    the self-chosen pseudonym and the only identifier there is
    (``docs/design-kompas.md`` 2.4)."""
    subs = db.query(FormSubmission).filter(FormSubmission.form_id == form.id).order_by(FormSubmission.created_at).all()
    out: list[CompassPoint] = []
    for sub in subs:
        place = places.get(sub.id)
        if place is None:
            # A submission with no answer rows at all: it exists, so it
            # is on the map, at the origin like anybody who said
            # nothing.
            place = compass.Position(0.0, 0.0, 0, 0)
        out.append(CompassPoint(name=sub.display_name, x=place.x, y=place.y, you=sub.id == you))
    return out


def compass_axis_summaries(db: Session, form: Form, places: dict[str, compass.Position]) -> list[CompassAxisSummary]:
    """The two axes, each with where the room sits on it.

    Read by the organiser's summary and by every respondent's result,
    so the band under one person's marker and the band on the
    organiser's page are the same number rather than two computations
    that can drift apart."""
    placed = list(places.values())
    out: list[CompassAxisSummary] = []
    for row in compass.axes_of(db, form.id):
        stats = compass.axis_stats(placed, row.axis)
        out.append(
            CompassAxisSummary(
                axis=CompassAxisOut.model_validate(row),
                average=stats[0] if stats else None,
                ci_low=stats[1] if stats else None,
                ci_high=stats[2] if stats else None,
            )
        )
    return out


def compass_summary(db: Session, form: Form, questions: list[FormQuestion]) -> CompassSummary | None:
    """The kompas half of the organiser's summary: the two axes with
    where the room sits on each, and every dot. ``None`` on the two
    products that place nobody."""
    if form.mode != "compass":
        return None
    places = compass_places(db, form, questions)
    return CompassSummary(
        axes=compass_axis_summaries(db, form, places),
        points=compass_points(db, form, places),
    )


def quiz_submissions(db: Session, form_id: str) -> list[QuizSubmissionOut]:
    """The organiser's list of played quizzes: the survey projection
    plus what each one scored, marked against the quiz as it stands
    now (``services/quiz``)."""
    questions = _questions(db, form_id)
    grouped = quizzes.rows_by_submission(db, form_id)
    out_of = quizzes.max_score(questions)
    return [
        QuizSubmissionOut(
            submission_id=row.submission_id,
            display_name=row.display_name,
            created_at=row.created_at,
            score=quizzes.score_of(questions, grouped.get(row.submission_id, [])),
            max_score=out_of,
            answers=row.answers,
            link_recovered_at=row.link_recovered_at,
        )
        for row in submissions(db, form_id, mode="quiz")
    ]


def submissions(db: Session, form_id: str, *, mode: str = "survey") -> list[FormSubmissionOut]:
    """Per-submission rows for the CSV export, keyed by question id.
    One ``FormSubmissionOut`` per fill-out, carrying the pseudonym
    (``display_name``, NULL = anonymous); the answer value matches the
    question kind (int / str / list[str]).

    Privacy: the submission id is opaque and the only respondent
    identifier is the self-chosen pseudonym."""
    questions = _questions(db, form_id)
    kinds = {q.id: q.kind for q in questions}
    # Two more CSV columns on a kompas, derived like everything else
    # about a position (``services/compass``).
    places = compass.positions(db, questions, form_id) if mode == "compass" else {}
    subs = db.query(FormSubmission).filter(FormSubmission.form_id == form_id).order_by(FormSubmission.created_at).all()
    if not subs:
        return []
    sub_ids = [s.id for s in subs]
    answers: dict[str, dict[str, int | str | list[str]]] = {sid: {} for sid in sub_ids}
    for r in db.query(FormResponse).filter(FormResponse.submission_id.in_(sub_ids)).all():
        kind = kinds.get(r.question_id)
        if kind is None:
            continue
        if kind in ("rating", "number") and r.answer_int is not None:
            answers[r.submission_id][r.question_id] = r.answer_int
        elif kind in _TEXT_KINDS and r.answer_text is not None:
            answers[r.submission_id][r.question_id] = r.answer_text
        elif kind in _CHOICE_KINDS and r.answer_choices is not None:
            answers[r.submission_id][r.question_id] = list(r.answer_choices)

    return [
        FormSubmissionOut(
            submission_id=s.id,
            display_name=s.display_name,
            created_at=s.created_at,
            answers=answers[s.id],
            x=places[s.id].x if s.id in places else None,
            y=places[s.id].y if s.id in places else None,
            link_recovered_at=s.link_recovered_at,
        )
        for s in subs
    ]
