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
  — organiser-side reads for the details page. ``submissions_csv``
  is the download, pivoted into columns by the database. Pure SQL
  aggregation, no router fixture needed.

* ``query`` — the only place the ``forms`` table is read from. Every
  read names the mode it means, because the table holds both products
  (``docs/design-quizzes.md``) and a read that forgets puts quizzes in
  the forms list. ``tests/test_form_modes.py`` greps the tree for
  anyone querying it anywhere else.

Chapter-scoped lookups live in ``services.access`` (``get_form_for_user``,
``form_scope_filter``) alongside the event equivalents; they take the
mode for the same reason.
"""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast, get_args

from fastapi import HTTPException
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Query, Session

from ..models import (
    Chapter,
    CompassAxis,
    Form,
    FormQuestion,
    FormQuestionOption,
    FormResponse,
    FormResponseChoice,
    FormSubmission,
    User,
)
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
)
from . import access, compass, numbers, public_access, quizzes, tenancy
from . import archive as archive_svc
from . import image as image_svc
from .ratings import rating_distribution

if TYPE_CHECKING:
    from ..schemas.forms import CompassAxisIn, FormQuestionIn


# Single source of truth for the supported kinds: the public
# ``QuestionKind`` literal. ``_CHOICE_KINDS`` is the subset that
# carries an options list.
ALLOWED_KINDS: Final[frozenset[str]] = frozenset(get_args(QuestionKind))
_CHOICE_KINDS: Final[frozenset[str]] = frozenset({"multiple_choice", "multiple_answer"})
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
            cleaned = [o.label.strip() for o in q.options if o.label.strip()]
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


def _apply_options(
    db: Session,
    question: FormQuestion,
    payload: Sequence[Any],
    *,
    scored: bool,
    pointed: bool,
) -> None:
    """Diff-apply one question's choices, matched by id.

    The same shape as the question diff a level up, for the same reason:
    an option carrying an id is the option the answers already point at,
    so a rename is an update to ``label`` and nothing detaches. An option
    with no id is new. One on disk that the payload no longer mentions is
    deleted, and the cascade takes the ticks with it, which is the
    destructive edit ``docs/design-question-edits.md`` gates.

    ``pole`` and ``is_correct`` are dropped unless the product asks for
    them, on the same terms as the question's own key and direction:
    decided here rather than trusted from the payload.
    """
    existing = {o.id: o for o in question.options}
    seen: set[str] = set()
    for ordinal, opt in enumerate(payload, start=1):
        pole = opt.pole if pointed and question.kind == "multiple_choice" else None
        correct = bool(opt.is_correct) if scored else False
        if opt.id and opt.id in existing:
            row = existing[opt.id]
            row.ordinal = ordinal
            row.label = opt.label.strip()
            row.pole = pole
            row.is_correct = correct
            seen.add(opt.id)
        else:
            # A fresh uuid always, so a client naming another question's
            # option cannot capture it. Same rule as the questions.
            db.add(
                FormQuestionOption(
                    question_id=question.id,
                    ordinal=ordinal,
                    label=opt.label.strip(),
                    pole=pole,
                    is_correct=correct,
                )
            )
    for oid, row in existing.items():
        if oid not in seen:
            db.delete(row)


def count_destroyed_answers(db: Session, form_id: str, questions: Sequence[Any]) -> int:
    """How many stored answers this save would delete.

    Three edits destroy answers, and they are the same three however the
    organiser arrives at them (``docs/design-question-edits.md``):

    * a question the payload no longer mentions,
    * a question whose kind changed, which is a different question and
      so replaces the row,
    * an option the payload no longer mentions.

    Counted before anything is written, so the caller can refuse the
    save and say what it would have cost. No double counting: the
    options of a question that is going are skipped, because its answers
    are already in the first total.
    """
    existing = {q.id: q for q in db.query(FormQuestion).filter(FormQuestion.form_id == form_id).all()}
    if not existing:
        return 0
    submitted = {q.id: q for q in questions if q.id}

    doomed_questions = [qid for qid, row in existing.items() if qid not in submitted or submitted[qid].kind != row.kind]
    doomed_options: list[str] = []
    for qid, row in existing.items():
        if qid in doomed_questions:
            continue
        kept = {o.id for o in submitted[qid].options if o.id}
        doomed_options.extend(o.id for o in row.options if o.id not in kept)

    total = 0
    if doomed_questions:
        total += (
            db.query(func.count(FormResponse.id)).filter(FormResponse.question_id.in_(doomed_questions)).scalar() or 0
        )
    if doomed_options:
        total += (
            db.query(func.count(FormResponseChoice.id))
            .filter(FormResponseChoice.option_id.in_(doomed_options))
            .scalar()
            or 0
        )
    return int(total)


def apply_questions(
    db: Session,
    form_id: str,
    questions: list["FormQuestionIn"],
    mode: str,
    axes: list["CompassAxisIn"] | None = None,
    *,
    confirmed: bool = False,
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

    An edit that would delete stored answers is refused unless
    ``confirmed``. The organiser is told how many and asked again, rather
    than finding out from a report that no longer adds up
    (``docs/design-question-edits.md``).

    Caller commits the session."""
    _validate_questions(questions, mode, list(axes or []))
    if not confirmed:
        doomed = count_destroyed_answers(db, form_id, questions)
        if doomed:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This removes {doomed} given {'answer' if doomed == 1 else 'answers'}. Save again to confirm."
                ),
            )

    existing = {q.id: q for q in db.query(FormQuestion).filter(FormQuestion.form_id == form_id).all()}
    seen_ids: set[str] = set()
    for ordinal, payload in enumerate(questions, start=1):
        # Kind-aware field normalisation. Non-choice kinds get an
        # empty options list regardless of what the client sent;
        # non-rating kinds drop the scale labels. Keeps the stored
        # row tidy and makes the public form's render kind-driven
        # without per-kind defensive checks.
        # Choices are rows, diffed by id like the questions themselves.
        # A payload option carrying an id updates that row, so a rename
        # is a label edit and every answer stays pointed at it.
        wanted_options = [o for o in payload.options if o.label.strip()] if payload.kind in _CHOICE_KINDS else []
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
        tolerance = payload.tolerance if scored and payload.kind == "number" else None
        # The direction, on the same terms: only a kompas has one, and
        # only on the half of the question its kind puts it on.
        pointed = mode == "compass"
        pole = payload.pole if pointed and payload.kind == "rating" else None

        # A kind change is a different question, not an edit to this one:
        # every stored answer sits in a column the new kind does not read.
        # So it falls through to the insert below, the old row is left out
        # of ``seen_ids``, and the delete pass takes it and its answers.
        # That is what retyping a question already does, and the two mean
        # the same thing to an organiser (``docs/design-question-edits``).
        if payload.id and payload.id in existing and existing[payload.id].kind == payload.kind:
            row = existing[payload.id]
            row.ordinal = ordinal
            row.kind = payload.kind
            row.prompt = payload.prompt.strip()
            row.required = required
            row.low_label = low_label
            row.high_label = high_label
            row.min_value = min_value
            row.max_value = max_value
            row.step = step
            row.points = points
            row.correct_int = correct_int
            row.correct_text = correct_text
            row.tolerance = tolerance
            row.pole = pole
            _apply_options(db, row, wanted_options, scored=scored, pointed=pointed)
            seen_ids.add(payload.id)
        else:
            # Insert. An id submitted that doesn't exist on disk is
            # ignored — we always mint a fresh uuid for new rows so
            # a client guessing at ids can't collide with another
            # form's question.
            db.add(
                fresh := FormQuestion(
                    form_id=form_id,
                    ordinal=ordinal,
                    kind=payload.kind,
                    prompt=payload.prompt.strip(),
                    required=required,
                    low_label=low_label,
                    high_label=high_label,
                    min_value=min_value,
                    max_value=max_value,
                    step=step,
                    points=points,
                    correct_int=correct_int,
                    correct_text=correct_text,
                    tolerance=tolerance,
                    pole=pole,
                )
            )
            db.flush()
            _apply_options(db, fresh, wanted_options, scored=scored, pointed=pointed)

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


# The columns the projections below read. A GET selects exactly these;
# a write route hands over the ORM entity it just saved, which answers
# the same attribute names, so one projection serves both.
LIST_COLUMNS = (
    Form.id,
    Form.slug,
    Form.mode,
    Form.name_nl,
    Form.name_en,
    Form.locale,
    Form.chapter_id,
    Form.archived_at,
    Form.created_at,
)
FULL_COLUMNS = (
    *LIST_COLUMNS,
    Form.description_nl,
    Form.description_en,
    Form.image_path,
    Form.image_artist_instagram,
    Form.reveal_answers,
    Form.answers_editable,
    Form.name_required,
)


def list_for_user(db: Session, user: User, mode: str, chapter_id: str | None) -> list[FormListOut]:
    """The organiser's list of one product, in one statement.

    The row, its chapter's name and how many people filled it in, asked
    together instead of as three round trips stitched back together in
    Python. The count is a scalar subquery rather than a join to
    ``form_submissions``, so one form stays one row."""
    submissions_count = select(func.count(FormSubmission.id)).where(FormSubmission.form_id == Form.id).scalar_subquery()
    rows = db.execute(
        select(*LIST_COLUMNS, Chapter.name.label("chapter_name"), submissions_count.label("submission_count"))
        .select_from(Form)
        .outerjoin(Chapter, and_(Chapter.id == Form.chapter_id, Chapter.deleted_at.is_(None)))
        # The table holds three products, so the mode predicate is part
        # of every read of it (``query``).
        .where(access.list_filter(db, user, Form, chapter_id), Form.mode == mode, Form.archived_at.is_(None))
        .order_by(Form.created_at.desc())
    ).all()
    return [
        FormListOut(
            id=r.id,
            slug=r.slug,
            mode=as_mode(r.mode),
            name_nl=r.name_nl,
            name_en=r.name_en,
            locale=r.locale,
            chapter_id=r.chapter_id,
            chapter_name=r.chapter_name,
            archived=r.archived_at is not None,
            created_at=r.created_at,
            submission_count=int(r.submission_count or 0),
        )
        for r in rows
    ]


def enrich(db: Session, forms: Sequence[Any]) -> list[FormListOut]:
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


@dataclass(frozen=True, slots=True)
class LoadedOption:
    """One choice of a question, as the read hands it over.

    A column-for-column stand-in for the ``form_question_options`` row,
    built from the JSON the questions query gathers, so every caller
    reads ``o.label`` and ``o.is_correct`` the same way whichever path
    loaded it.
    """

    id: str
    ordinal: int
    label: str
    pole: str | None
    is_correct: bool


class LoadedQuestion:
    """A question row with its choices attached.

    The graders, the kompas and the DTOs all ask a question for its
    ``options``, so the read hands back something that answers that,
    rather than a bare row plus a dictionary every caller has to carry.
    The fields mirror the columns; ``options`` is the rows from
    ``form_question_options``, in their own order.

    The columns are copied onto the instance rather than reached through
    a ``__getattr__`` that forwards to the row. The kompas reads a
    question's fields once per answer per submission, and forwarding
    made that a Python-level call every time: 77,000 of them to write
    one CSV of five hundred, which profiled at a fifth of the whole
    request.
    """

    __slots__ = ("row", "options", "__dict__")

    def __init__(self, row: Any, options: list[Any]) -> None:
        self.row = row
        self.options = options
        self.__dict__.update(row._mapping)


# The questions and their choices, in one statement.
#
# A question's options are gathered by the database rather than read as
# a second result set and grouped here: the join happens inside the
# aggregate, so one question stays one row and nothing multiplies. Every
# read path in this file goes through it, so the saving is a round trip
# on the details page, the public page, the summary and the CSV alike.
_QUESTIONS_SQL = text("""
SELECT q.*,
       coalesce(
           (SELECT json_agg(json_build_object(
                       'id', o.id,
                       'ordinal', o.ordinal,
                       'label', o.label,
                       'pole', o.pole,
                       'is_correct', o.is_correct
                   ) ORDER BY o.ordinal)
            FROM form_question_options o WHERE o.question_id = q.id),
           '[]'::json
       ) AS options
FROM form_questions q
WHERE q.form_id = :form_id
ORDER BY q.ordinal
""")


def _questions(db: Session, form_id: str) -> Sequence[Any]:
    """The form's questions in display order, each carrying its choices.

    One query whatever the form asks. Core rather than the ORM, because
    a question is never written back through this path
    (``apply_questions`` owns that)."""
    return [
        LoadedQuestion(row, [LoadedOption(**o) for o in row.options])
        for row in db.execute(_QUESTIONS_SQL, {"form_id": form_id}).all()
    ]


def questions_of(db: Session, form_id: str) -> Sequence[Any]:
    """The question rows, for a caller that has to mark answers against
    them (``routers/form`` asking ``services/quiz`` for the score
    stats)."""
    return _questions(db, form_id)


def _row_extras(db: Session, form: Any) -> tuple[str | None, int]:
    """The chapter's name and how many people filled the form in.

    Two scalars off two different tables, asked together: neither has a
    row to hang off, so they were two round trips for two numbers. The
    list endpoint already reads them this way, as subqueries beside the
    form.
    """
    row = db.execute(
        select(
            select(Chapter.name)
            .where(Chapter.id == form.chapter_id, Chapter.deleted_at.is_(None))
            .scalar_subquery()
            .label("chapter_name"),
            select(func.count(FormSubmission.id))
            .where(FormSubmission.form_id == form.id)
            .scalar_subquery()
            .label("submissions"),
        )
    ).one()
    return (row.chapter_name if form.chapter_id else None), int(row.submissions or 0)


def to_out(db: Session, form: Any) -> FormOut:
    """Single-form organiser DTO: the list-row fields plus the full
    question list. One statement for the two derived numbers, one for
    the questions."""
    chapter_name, submissions_total = _row_extras(db, form)
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
        submission_count=submissions_total,
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
        # Derived per request from each option's own pole, in the
        # options' order, so the page can print a count beside the
        # direction that earned it.
        option_poles=[o.pole or "" for o in q.options] if any(o.pole for o in q.options) else None,
        **fields,  # type: ignore[arg-type]
    )


# One statement for every tally an answers page shows.
#
# The three shapes are three grains: a rating wants a row per distinct
# value, a choice question a row per option, an open question every
# answer it was given. Each is aggregated in its own CTE and joined back
# to one row per question, which is why joining the ticks cannot
# multiply anything: the join happens inside its own subquery, and only
# the finished tally comes out.
#
# The choice tally is a plain join now that a tick is a row keyed by
# option id, so it counts by id and the labels are applied afterwards.
# A renamed option keeps its answers because the count never touched
# the text.
_AGGREGATES_SQL = text("""
WITH resp AS (
    SELECT id, question_id, answer_int, answer_text, created_at
    FROM form_responses WHERE form_id = :form_id
),
numbers AS (
    SELECT question_id, json_agg(json_build_array(value, n) ORDER BY value) AS pairs
    FROM (
        SELECT question_id, answer_int AS value, count(*) AS n
        FROM resp WHERE answer_int IS NOT NULL GROUP BY 1, 2
    ) counted
    GROUP BY question_id
),
options AS (
    SELECT question_id, json_agg(json_build_array(option_id, n)) AS pairs
    FROM (
        SELECT r.question_id, c.option_id, count(*) AS n
        FROM resp r JOIN form_response_choices c ON c.response_id = r.id
        GROUP BY 1, 2
    ) counted
    GROUP BY question_id
),
option_totals AS (
    SELECT r.question_id, count(DISTINCT r.id)::int AS n
    FROM resp r JOIN form_response_choices c ON c.response_id = r.id
    GROUP BY 1
),
texts AS (
    SELECT question_id,
           json_agg(answer_text ORDER BY created_at DESC) AS answers,
           count(*)::int AS n
    FROM resp WHERE answer_text IS NOT NULL GROUP BY 1
)
SELECT q.id AS question_id,
       numbers.pairs AS number_pairs,
       options.pairs AS option_pairs,
       coalesce(option_totals.n, 0) AS option_total,
       texts.answers AS texts,
       coalesce(texts.n, 0) AS text_total
FROM form_questions q
LEFT JOIN numbers ON numbers.question_id = q.id
LEFT JOIN options ON options.question_id = q.id
LEFT JOIN option_totals ON option_totals.question_id = q.id
LEFT JOIN texts ON texts.question_id = q.id
WHERE q.form_id = :form_id
""")


def _pairs(row: Any, field: str) -> list[tuple[Any, int]]:
    """A tally column as ``[(value, count)]``. ``json_agg`` gives back
    ``null`` for a question nobody answered, which is an empty tally."""
    if row is None:
        return []
    raw = getattr(row, field)
    return [(value, int(n)) for value, n in raw] if raw else []


def question_aggregates(
    db: Session,
    form_id: str,
    questions: Sequence[Any],
    shares: Mapping[str, float],
) -> list[FormQuestionSummary]:
    """One ``FormQuestionSummary`` per question, ordinal-ordered.
    Per-kind shape:

    * ``rating`` — 5-bucket distribution + average.
    * ``number`` — average, lowest, highest.
    * ``text`` / ``short_text`` — raw answers, newest first.
    * ``multiple_choice`` / ``multiple_answer`` — option → count map.

    Every tally comes from one statement (``_AGGREGATES_SQL``) whatever
    the form asks and however many questions it has. ``shares`` is the
    marking half, which a quiz reads alongside its scores
    (``quizzes.summary_stats``) and every other mode leaves empty.

    """
    if not questions:
        return []

    tallies = {r.question_id: r for r in db.execute(_AGGREGATES_SQL, {"form_id": form_id}).all()}

    summaries: list[FormQuestionSummary] = []
    for q in questions:
        share = shares.get(q.id)
        row = tallies.get(q.id)
        if q.kind == "rating":
            distribution, total, average = rating_distribution(_pairs(row, "number_pairs"))
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
            values = [value for value, n in _pairs(row, "number_pairs") for _ in range(n)]
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
            answers = list(row.texts) if row is not None and row.texts else []
            summaries.append(_summary(q, share, response_count=len(answers), texts=answers))
        elif q.kind in _CHOICE_KINDS:
            # Seeded from the question's own options so one nobody picked
            # still shows as zero, and a stored answer whose option has
            # since been renamed away simply does not land anywhere.
            # Keyed by option id in SQL, labelled here. An option the
            # organiser has since renamed still carries its answers,
            # because the tally joined on the id.
            tally = dict(_pairs(row, "option_pairs"))
            counts: dict[str, int] = {o.label: int(tally.get(o.id, 0)) for o in q.options}
            summaries.append(
                _summary(
                    q,
                    share,
                    response_count=(row.option_total if row is not None else 0),
                    choice_counts=counts,
                )
            )
        else:
            # Unknown kind — unreachable in practice (validated on
            # write + DB CHECK), but the summary endpoint shouldn't
            # crash on a malformed row.
            summaries.append(_summary(q, share, response_count=0))
    return summaries


# One row per submission, answers already in column order.
#
# ``cells`` is the pivot: the question list is unnested with its
# ordinal, left-joined to what this submission said, so a question
# nobody answered is an empty cell rather than a missing column and
# every row is the same width as the header. A tick is written as the
# option's label because that is what the respondent saw, and a
# multiple pick joins its labels with a semicolon.
_CSV_SQL: Final[str] = """
WITH cell AS (
    SELECT r.submission_id,
           q.ordinal,
           CASE
               WHEN q.kind IN ('rating', 'number') THEN r.answer_int::text
               WHEN q.kind IN ('multiple_choice', 'multiple_answer') THEN (
                   SELECT string_agg(o.label, '; ' ORDER BY o.ordinal)
                   FROM form_response_choices c
                   JOIN form_question_options o ON o.id = c.option_id
                   WHERE c.response_id = r.id
               )
               ELSE r.answer_text
           END AS value
    FROM form_responses r
    JOIN form_questions q ON q.id = r.question_id
    WHERE r.form_id = :form_id
),
column_of AS (
    SELECT ordinal FROM form_questions WHERE form_id = :form_id
)
SELECT coalesce(s.display_name, 'Anonymous') AS name,
       to_char(s.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS submitted_at,
       {places}
       (
           SELECT coalesce(array_agg(coalesce(cell.value, '') ORDER BY column_of.ordinal), '{{}}')
           FROM column_of
           LEFT JOIN cell ON cell.submission_id = s.id AND cell.ordinal = column_of.ordinal
       ) AS cells
FROM form_submissions s
{join}
WHERE s.form_id = :form_id
ORDER BY s.created_at
"""

# A kompas carries its two coordinates beside the answers that made
# them, read from the same statement the map is drawn from.
_CSV_PLACES: Final[str] = f"LEFT JOIN (\n{compass.PLACES_SQL}\n) place ON place.submission_id = s.id"


def submissions_csv(db: Session, form_id: str, *, mode: str) -> tuple[list[str], Iterator[Sequence[Any]]]:
    """The organiser's download: the header, and the rows behind it.

    The header is English but for the questions, which are the
    organiser's own words. The rows stream: the database pivots the
    answers into columns and this hands them straight to the writer
    (``services/csv_export``)."""
    questions = _questions(db, form_id)
    compassed = mode == "compass"
    header = ["Name", "Submitted at", *(["X", "Y"] if compassed else []), *(q.prompt for q in questions)]
    statement = text(
        _CSV_SQL.format(
            places="place.x, place.y," if compassed else "",
            join=_CSV_PLACES if compassed else "",
        )
    )
    result = db.execute(
        statement,
        compass.params(form_id) if compassed else {"form_id": form_id},
    )
    rows = ([row.name, row.submitted_at, *([row.x, row.y] if compassed else []), *row.cells] for row in result)
    return header, rows


def compass_summary(db: Session, form: Any, *, you: str | None = None) -> CompassSummary | None:
    """The kompas half of a page: the two axes with where the room sits
    on each, and every dot. ``None`` on the two products that place
    nobody.

    One read (``compass.room``): the dots and the axes are the same
    coordinates counted at two grains. ``you`` marks one dot as the
    reader's own, which the organiser's copy leaves out because on
    their page nobody is "you"."""
    if form.mode != "compass":
        return None
    room = compass.room(db, form.id)
    return CompassSummary(
        axes=[
            CompassAxisSummary(
                axis=CompassAxisOut.model_validate(row),
                average=room.axes.get(row.axis, (None, None, None))[0],
                ci_low=room.axes.get(row.axis, (None, None, None))[1],
                ci_high=room.axes.get(row.axis, (None, None, None))[2],
            )
            for row in compass.axes_of(db, form.id)
        ],
        points=[CompassPoint(name=dot.name, x=dot.x, y=dot.y, you=dot.submission_id == you) for dot in room.dots],
    )


def submissions(db: Session, form_id: str) -> list[FormSubmissionOut]:
    """Who filled the form in and when, oldest first.

    Not what they said: that is the download's business, written by the
    database (``submissions_csv``). This list is read by the page that
    hands somebody their edit link back, so it carries the pseudonym
    and whether the link has already been recovered.

    Privacy: the submission id is opaque and the only respondent
    identifier is the self-chosen pseudonym."""
    rows = db.execute(
        select(
            FormSubmission.id,
            FormSubmission.display_name,
            FormSubmission.created_at,
            FormSubmission.link_recovered_at,
        )
        .where(FormSubmission.form_id == form_id)
        .order_by(FormSubmission.created_at)
    ).all()
    return [
        FormSubmissionOut(
            submission_id=r.id,
            display_name=r.display_name,
            created_at=r.created_at,
            link_recovered_at=r.link_recovered_at,
        )
        for r in rows
    ]
