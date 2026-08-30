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
  ``PUBLIC_BASE_URL/{f,q}/{slug}``. Mirrors the events QR endpoint
  one-to-one — same SVG-path rendering, same per-process LRU,
  same 24h browser cache.

Archived forms 410 on the JSON + submit endpoints; QR is served
for any live form (archived forms aren't displayed anywhere
that surfaces the QR).

Mounted once per product (``docs/design-quizzes.md``,
``docs/design-kompas.md``). They differ in a handful of places and
share the rest:

* a quiz is graded on submit and a kompas is placed on submit, so the
  response is a result rather than an acknowledgement;
* a quiz submission cannot be edited at all, because changing an answer
  after seeing the score is a second attempt rather than a correction.
  The token opens the result read-only. A kompas submission stays
  editable like a questionnaire's, because changing your answer after
  seeing the map is changing your mind. The name comes with the
  submission, from the cover page, on both;
* withdrawing works on all three: "delete what I sent" is a privacy
  right. On a quiz it costs the withdrawer their score and on a kompas
  it takes their dot off the map, so it is no loophole either way.
"""

from collections.abc import Callable
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Form, FormQuestion, FormResponse, FormResponseChoice, FormSubmission
from ..schemas.forms import (
    CompassAnswerResult,
    CompassResultOut,
    FormAnswerIn,
    FormEditOut,
    FormSubmitAck,
    FormSubmitIn,
    PublicFormOut,
    QuizAnswerResult,
    QuizResultOut,
)
from ..services import compass, edit_token, limits, public_access, quizzes, traffic
from ..services import forms as forms_svc
from ..services.qr import render_qr
from ..services.rate_limit import Limits, limiter

# Public-facing base URL — validated at import time (HttpUrl),
# never empty. Same constant ``events_public.py`` uses.
PUBLIC_BASE_URL = str(settings.public_base_url).rstrip("/")

logger = structlog.get_logger()


def _named(name: str):
    """Rename an endpoint before the decorators above it see it.

    FastAPI and slowapi both key off ``__name__``, and a factory that
    builds the same routes twice hands them two functions with one
    name. slowapi then holds two limits against a single key and
    charges every request twice: found by ``test_submit_rate_limit_fires``
    firing on the 11th of 20 allowed submissions. Decorators apply
    bottom-up, so this one runs first and the two mounts register as
    ``submit_form`` and ``submit_quiz``."""

    def wrap(func):  # type: ignore[no-untyped-def]
        func.__name__ = name
        func.__qualname__ = name
        return func

    return wrap


# How to build the submission behind an edit-link token, per product.
# Populated by ``build_router``; read by ``routers/spa.py``, which
# inlines the result into the HTML for a ``?s=`` link so the page paints
# without a round-trip for something the server already had.
SUBMISSION_FOR_TOKEN: dict[str, Callable[[Session, str], BaseModel]] = {}


def build_router(mode: str, *, prefix: str, tag: str, surface: str, noun: str, public_prefix: str) -> APIRouter:
    """The public surface for one of the three products.

    ``surface`` is the traffic counter name, ``noun`` names the log
    events so a submission still says which product it was, and
    ``public_prefix`` is the one-letter path the QR code points at:
    ``/f/{slug}`` for a questionnaire, ``/q/{slug}`` for a quiz,
    ``/k/{slug}`` for a kompas."""
    _MODE = mode
    router = APIRouter(prefix=prefix, tags=[tag])
    is_quiz = mode == "quiz"
    is_compass = mode == "compass"
    # The ceiling bucket in ``services/limits``: each product gets its
    # own, so a personal account's kompassen do not eat into its
    # questionnaires.
    _KIND = {"quiz": "quiz", "compass": "compass"}.get(mode, "form")

    def _resolve_form(db: Session, slug: str) -> Form:
        """Resolve a slug to a live form. Archived forms 410. Unknown
        slugs 410 too — the public surface doesn't distinguish "never
        existed" from "archived since you bookmarked the link"; both
        look the same to the visitor and that's correct (no info
        leak)."""
        return forms_svc.resolve_public(db, slug, _MODE)

    def _form_questions(db: Session, form_id: str) -> list[FormQuestion]:
        return db.query(FormQuestion).filter(FormQuestion.form_id == form_id).order_by(FormQuestion.ordinal).all()

    @router.get("/by-slug/{slug}/qr.svg")
    def get_form_qr(slug: str, db: Session = Depends(get_db)) -> Response:
        """QR SVG for one slug. Resolves the form first so a typo'd
        slug 410s rather than 200ing with a wrong-target QR."""
        form = _resolve_form(db, slug)
        return Response(
            content=render_qr(f"{PUBLIC_BASE_URL}/{public_prefix}/{form.slug}"),
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
                if q.step and (ans.answer_int - (q.min_value or 0)) % q.step != 0:
                    raise HTTPException(status_code=400, detail=f"Question {q.id}: number is not on the step.")
                submitted[q.id] = {"answer_int": ans.answer_int}
            elif q.kind in ("text", "short_text"):
                text = (ans.answer_text or "").strip()
                if not text:
                    continue
                submitted[q.id] = {"answer_text": text}
            elif q.kind == "multiple_choice":
                choices = ans.answer_choices or []
                if not choices:
                    continue
                if len(choices) != 1:
                    raise HTTPException(status_code=400, detail=f"Question {q.id} expects one choice.")
                if choices[0] not in {o.id for o in q.options}:
                    raise HTTPException(status_code=400, detail=f"Question {q.id}: choice not in options.")
                submitted[q.id] = {"answer_choices": list(choices)}
            elif q.kind == "multiple_answer":
                choices = ans.answer_choices or []
                if not choices:
                    # On a quiz, ticking nothing is an answer: "none of
                    # these" is a position, and every question there is
                    # required, so refusing it would leave somebody
                    # stuck on a question they have answered. A
                    # questionnaire's required question still wants a
                    # tick.
                    if is_quiz:
                        submitted[q.id] = {"answer_choices": []}
                    continue
                option_ids = {o.id for o in q.options}
                invalid = [c for c in choices if c not in option_ids]
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

    def _write_responses(
        db: Session,
        form_id: str,
        submission_id: str,
        submitted: dict[str, dict[str, object]],
    ) -> None:
        for qid, fields in submitted.items():
            response = FormResponse(
                form_id=form_id,
                question_id=qid,
                submission_id=submission_id,
                answer_int=fields.get("answer_int"),  # type: ignore[arg-type]
                answer_text=fields.get("answer_text"),  # type: ignore[arg-type]
            )
            db.add(response)
            db.flush()
            # One row per tick, pointing at the option itself. The
            # answer survives the organiser renaming that option.
            for option_id in cast(list[str], fields.get("answer_choices") or []):
                db.add(FormResponseChoice(response_id=response.id, option_id=option_id))

    def _answers_for(db: Session, submission_id: str) -> dict[str, object]:
        out: dict[str, object] = {}
        picked: dict[str, list[str]] = {}
        for question_id, option_id in db.execute(
            select(FormResponse.question_id, FormResponseChoice.option_id)
            .join(FormResponseChoice, FormResponseChoice.response_id == FormResponse.id)
            .where(FormResponse.submission_id == submission_id)
        ).all():
            picked.setdefault(question_id, []).append(option_id)
        for r in db.query(FormResponse).filter(FormResponse.submission_id == submission_id).all():
            if r.answer_int is not None:
                out[r.question_id] = r.answer_int
            elif r.answer_text is not None:
                out[r.question_id] = r.answer_text
            elif r.question_id in picked:
                out[r.question_id] = picked[r.question_id]
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

    def _result(db: Session, form: Form, submission: FormSubmission, token: str) -> QuizResultOut:
        """The score, and what was right.

        Marked hererather than read from a stored number: the answers
        are what is kept, and an organiser who fixes a key or changes a
        weight means every score to follow (``services/quiz``). The
        rows are the answers this person actually gave, so the list and
        the score cannot disagree about what was in the quiz."""
        questions = {q.id: q for q in _form_questions(db, form.id)}
        rows = db.query(FormResponse).filter(FormResponse.submission_id == submission.id).all()
        # Marked by the database, against the same rules the organiser's
        # page reads, so a score here and a score there cannot differ.
        awarded = quizzes.earned_points(db, form.id, submission.id)
        answers = []
        score = 0
        for row in rows:
            q = questions.get(row.question_id)
            if q is None or q.points <= 0:
                continue
            earned = awarded.get(row.question_id, 0)
            score += earned
            answers.append(
                QuizAnswerResult(
                    question_id=q.id,
                    awarded=earned,
                    points=q.points,
                    correct=earned >= q.points,
                    given_int=row.answer_int,
                    given_text=row.answer_text,
                    given_choices=list(row.answer_choices) if row.answer_choices else None,
                    # The key travels only when the organiser left the
                    # reveal on. A quiz being run twice in one evening
                    # has it off.
                    correct_int=q.correct_int if form.reveal_answers else None,
                    correct_text=q.correct_text if form.reveal_answers else None,
                    # The key as labels: this is what the page prints,
                    # and it is only sent once the answer is in.
                    correct_choices=(
                        [o.label for o in q.options if o.is_correct] if form.reveal_answers and q.options else None
                    ),
                )
            )
        answers.sort(key=lambda a: questions[a.question_id].ordinal)
        return QuizResultOut(
            submission_id=submission.id,
            edit_token=token,
            score=score,
            max_score=quizzes.max_score(list(questions.values())),
            reveal_answers=form.reveal_answers,
            answers=answers,
        )

    def _compass_result(db: Session, form: Form, submission: FormSubmission, token: str) -> CompassResultOut:
        """Where this submission landed, the room around it, and every
        answer with the direction that was hidden until now.

        Computed here rather than read from a stored coordinate: the
        answers are what is kept, and an organiser who moves an option
        to the other side means every dot to move
        (``services/compass``). Reopening the link therefore also shows
        the room as it stands, not as it was."""
        questions = _form_questions(db, form.id)
        by_id = {q.id: q for q in questions}
        rows = db.query(FormResponse).filter(FormResponse.submission_id == submission.id).all()
        # Both the dot and the per-answer directions under it are worked
        # out by the database, from the same rules the map is drawn
        # from: nothing here re-derives a coordinate.
        place = compass.positions(db, form.id, submission.id).get(submission.id, compass.Position(0.0, 0.0, 0, 0))
        moved = compass.contributions(db, form.id, submission.id)
        answers: list[CompassAnswerResult] = []
        for row in rows:
            q = by_id.get(row.question_id)
            if q is None:
                continue
            found = moved.get(row.question_id)
            answers.append(
                CompassAnswerResult(
                    question_id=q.id,
                    kind=q.kind,
                    pole=q.pole,
                    option_poles=[o.pole or "" for o in q.options] if any(o.pole for o in q.options) else None,
                    given_int=row.answer_int,
                    given_choices=list(row.answer_choices) if row.answer_choices else None,
                    axis=found[0] if found else None,
                    value=found[1] if found else None,
                )
            )
        answers.sort(key=lambda a: by_id[a.question_id].ordinal)
        # The axes and the dots come out of one read, with this person's
        # own dot marked in it.
        room = forms_svc.compass_summary(db, form, you=submission.id)
        assert room is not None
        return CompassResultOut(
            submission_id=submission.id,
            edit_token=token,
            display_name=submission.display_name,
            link_recovered_at=submission.link_recovered_at,
            x=place.x,
            y=place.y,
            counted_x=place.counted_x,
            counted_y=place.counted_y,
            axes=room.axes,
            answers=answers,
            points=room.points,
        )

    @router.post(
        "/by-slug/{slug}/submit",
        # A survey acknowledges. A quiz answers with the result, which
        # is the first moment the key is allowed out of the server, and
        # a kompas with the map, which is the first moment the
        # directions are.
        response_model=QuizResultOut if is_quiz else CompassResultOut if is_compass else FormSubmitAck,
        status_code=201,
    )
    @limiter.limit(Limits.PUBLIC_SUBMIT)
    @_named(f"submit_{noun}")
    def submit_form(
        request: Request,
        slug: str,
        data: FormSubmitIn,
        db: Session = Depends(get_db),
    ) -> QuizResultOut | CompassResultOut | FormSubmitAck:
        """Accept one public submission. Mints a secret edit-link token
        (raw returned once; only its hash stored) so the respondent can
        come back to it. Nothing in the response links the submission
        back to a person beyond the self-chosen pseudonym."""
        form = _resolve_form(db, slug)
        public_access.assert_name_given(form, data.display_name)
        limits.assert_has_room_for_participant(db, form.tenant, _KIND, form.id)
        questions = _form_questions(db, form.id)
        submitted = _build_submitted(questions, data.answers)

        raw_token, token_hash = edit_token.new_edit_token()
        submission = FormSubmission(form_id=form.id, display_name=data.display_name, edit_token_hash=token_hash)
        db.add(submission)
        db.flush()  # need submission.id for the response rows
        _write_responses(db, form.id, submission.id, submitted)
        db.commit()
        logger.info(f"{noun}_submitted", form_id=form.id, submission_id=submission.id)
        traffic.record(surface, "submit")
        if is_quiz:
            return _result(db, form, submission, raw_token)
        if is_compass:
            return _compass_result(db, form, submission, raw_token)
        return FormSubmitAck(submission_id=submission.id, edit_token=raw_token)

    def _submission_out(db: Session, token: str) -> BaseModel:
        """What the page behind an edit-link token shows: a quiz's
        result, a kompas's map, or a questionnaire's current answers.
        One function so the ``by-token`` route and the inlined copy in
        the HTML shell can never render different things."""
        sub = _submission_by_token(db, token)
        if is_quiz or is_compass:
            form = db.get(Form, sub.form_id)
            assert form is not None  # the token resolver already validated it
            return _result(db, form, sub, token) if is_quiz else _compass_result(db, form, sub, token)
        return FormEditOut(
            display_name=sub.display_name,
            answers=_answers_for(db, sub.id),  # type: ignore[arg-type]
            link_recovered_at=sub.link_recovered_at,
        )

    SUBMISSION_FOR_TOKEN[mode] = _submission_out

    if is_quiz:

        @router.get("/by-token/{token}", response_model=QuizResultOut)
        def get_quiz_result(token: str, db: Session = Depends(get_db)) -> QuizResultOut:
            """The result again, later. Read-only on purpose: changing
            an answer after seeing the score is a second attempt, not a
            correction (``docs/design-quizzes.md`` part 3.4). There is
            no PUT on this path for a quiz."""
            return cast(QuizResultOut, _submission_out(db, token))

    elif is_compass:

        @router.get("/by-token/{token}", response_model=CompassResultOut)
        def get_compass_result(token: str, db: Session = Depends(get_db)) -> CompassResultOut:
            """The map again, later, drawn against the room as it
            stands. The per-answer rows carry what was given, so this
            one shape both renders the result and refills the walk
            behind the "change your answers" button."""
            return cast(CompassResultOut, _submission_out(db, token))

        @router.put("/by-token/{token}", response_model=CompassResultOut)
        @limiter.limit(Limits.PUBLIC_SUBMIT)
        @_named(f"update_submission_{noun}")
        def update_compass_submission(
            request: Request,
            token: str,
            data: FormSubmitIn,
            db: Session = Depends(get_db),
        ) -> CompassResultOut:
            """Change your mind. Unlike a quiz, this is a correction
            rather than a second attempt: a kompas has nothing to score
            and nothing to beat (``docs/design-kompas.md`` 5.4). The
            answer rows and the pseudonym are replaced, and the map
            comes back redrawn."""
            sub = _submission_by_token(db, token)
            form = db.get(Form, sub.form_id)
            assert form is not None
            public_access.assert_answers_editable(form)
            public_access.assert_name_given(form, data.display_name)
            submitted = _build_submitted(_form_questions(db, sub.form_id), data.answers)
            db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
            sub.display_name = data.display_name
            _write_responses(db, sub.form_id, sub.id, submitted)
            db.commit()
            logger.info(f"{noun}_submission_edited", form_id=sub.form_id, submission_id=sub.id)
            return _compass_result(db, form, sub, token)

    else:

        @router.get("/by-token/{token}", response_model=FormEditOut)
        def get_form_submission(token: str, db: Session = Depends(get_db)) -> FormEditOut:
            """Current values of a submission, for pre-filling the edit
            form. Gated by the secret token (the link)."""
            return cast(FormEditOut, _submission_out(db, token))

        @router.put("/by-token/{token}", response_model=FormEditOut)
        @limiter.limit(Limits.PUBLIC_SUBMIT)
        @_named(f"update_submission_{noun}")
        def update_form_submission(
            request: Request,
            token: str,
            data: FormSubmitIn,
            db: Session = Depends(get_db),
        ) -> FormEditOut:
            """Update a submission in place via its edit-link token.
            Replaces the submission's answer rows and the pseudonym."""
            sub = _submission_by_token(db, token)
            form = db.get(Form, sub.form_id)
            assert form is not None
            public_access.assert_answers_editable(form)
            public_access.assert_name_given(form, data.display_name)
            submitted = _build_submitted(_form_questions(db, sub.form_id), data.answers)
            db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
            sub.display_name = data.display_name
            _write_responses(db, sub.form_id, sub.id, submitted)
            db.commit()
            logger.info(f"{noun}_submission_edited", form_id=sub.form_id, submission_id=sub.id)
            return FormEditOut(
                display_name=sub.display_name,
                answers=_answers_for(db, sub.id),  # type: ignore[arg-type]
                link_recovered_at=sub.link_recovered_at,
            )

    @router.post("/by-token/{token}/withdraw", status_code=204)
    @limiter.limit(Limits.PUBLIC_SUBMIT)
    @_named(f"withdraw_submission_{noun}")
    def withdraw_form_submission(request: Request, token: str, db: Session = Depends(get_db)) -> None:
        """Withdraw a submission via its edit-link token — the respondent
        deleting their own answers. Removes the response rows and the
        submission; nothing else references either (pseudonymous, no email)."""
        sub = _submission_by_token(db, token)
        form_id = sub.form_id
        db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
        db.delete(sub)
        db.commit()
        logger.info(f"{noun}_submission_withdrawn", form_id=form_id)

    return router


router = build_router(
    "survey", prefix="/api/v1/form", tag="forms", surface="public_form", noun="form", public_prefix="f"
)
quiz_router = build_router(
    "quiz", prefix="/api/v1/quiz", tag="quizzes", surface="public_quiz", noun="quiz", public_prefix="q"
)
compass_router = build_router(
    "compass",
    prefix="/api/v1/compass",
    tag="compasses",
    surface="public_compass",
    noun="compass",
    public_prefix="k",
)
