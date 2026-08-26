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

Mounted twice, once per product (``docs/design-quizzes.md``). The two
differ in exactly three places and share the rest:

* a quiz is graded on submit, so the response is a result rather than
  an acknowledgement;
* a quiz submission cannot be edited, because changing an answer after
  seeing the score is a second attempt rather than a correction. The
  token opens the result read-only;
* withdrawing works on both: "delete what I sent" is a privacy right,
  and it costs the withdrawer their score, so it is no loophole.
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
    QuizAnswerResult,
    QuizResultOut,
)
from ..services import edit_token, limits, public_access, quizzes, traffic
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


def build_router(mode: str, *, prefix: str, tag: str, surface: str, noun: str) -> APIRouter:
    """The public surface for one of the two products.

    ``surface`` is the traffic counter name and ``noun`` names the log
    events, so a submission still says which product it was."""
    _MODE = mode
    router = APIRouter(prefix=prefix, tags=[tag])
    is_quiz = mode == "quiz"
    # The ceiling bucket in ``services/limits``: a personal account's
    # quizzes and questionnaires each get their own.
    _KIND = "quiz" if is_quiz else "form"

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

    def _write_responses(
        db: Session,
        form_id: str,
        submission_id: str,
        submitted: dict[str, dict[str, object]],
        graded: list[FormQuestion] | None,
    ) -> None:
        by_id = {q.id: q for q in graded or []}
        for qid, fields in submitted.items():
            question = by_id.get(qid)
            db.add(
                FormResponse(
                    form_id=form_id,
                    question_id=qid,
                    submission_id=submission_id,
                    answer_int=fields.get("answer_int"),  # type: ignore[arg-type]
                    answer_text=fields.get("answer_text"),  # type: ignore[arg-type]
                    answer_choices=fields.get("answer_choices"),  # type: ignore[arg-type]
                    # What this answer earned, at the moment it was
                    # given. Null on a survey, and on a quiz question
                    # worth nothing.
                    awarded=quizzes.grade(question, fields) if question is not None else None,
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

    def _result(db: Session, form: Form, submission: FormSubmission, token: str) -> QuizResultOut:
        """The score, and what was right. Assembled from the stored
        grades rather than by re-grading, so a result opened months
        later still says what it said on the day, whatever the organiser
        has changed since."""
        awarded = {r.question_id: r for r in db.query(FormResponse).filter(FormResponse.submission_id == submission.id)}
        answers = []
        for q in _form_questions(db, form.id):
            if q.points <= 0:
                continue
            row = awarded.get(q.id)
            earned = int(row.awarded or 0) if row is not None else 0
            answers.append(
                QuizAnswerResult(
                    question_id=q.id,
                    awarded=earned,
                    points=q.points,
                    correct=earned >= q.points,
                    # The key travels only when the organiser left the
                    # reveal on. A quiz being run twice in one evening
                    # has it off.
                    correct_int=q.correct_int if form.reveal_answers else None,
                    correct_text=q.correct_text if form.reveal_answers else None,
                    correct_choices=q.correct_choices if form.reveal_answers else None,
                )
            )
        return QuizResultOut(
            submission_id=submission.id,
            edit_token=token,
            score=int(submission.score or 0),
            max_score=int(submission.max_score or 0),
            reveal_answers=form.reveal_answers,
            answers=answers,
        )

    @router.post(
        "/by-slug/{slug}/submit",
        # A survey acknowledges; a quiz answers with the result, which
        # is the first moment the key is allowed out of the server.
        response_model=QuizResultOut if is_quiz else FormSubmitAck,
        status_code=201,
    )
    @limiter.limit(Limits.PUBLIC_SUBMIT)
    @_named(f"submit_{noun}")
    def submit_form(
        request: Request,
        slug: str,
        data: FormSubmitIn,
        db: Session = Depends(get_db),
    ) -> QuizResultOut | FormSubmitAck:
        """Accept one public submission. Mints a secret edit-link token
        (raw returned once; only its hash stored) so the respondent can
        come back to it. Nothing in the response links the submission
        back to a person beyond the self-chosen pseudonym."""
        form = _resolve_form(db, slug)
        limits.assert_has_room_for_participant(db, form.tenant, _KIND, form.id)
        questions = _form_questions(db, form.id)
        submitted = _build_submitted(questions, data.answers)

        raw_token, token_hash = edit_token.new_edit_token()
        submission = FormSubmission(form_id=form.id, display_name=data.display_name, edit_token_hash=token_hash)
        if is_quiz:
            # Graded here, from the stored key, and stored with the
            # total it was out of: an organiser can edit the quiz
            # afterwards and an old score has to stay readable.
            submission.score = sum(quizzes.grade(q, submitted.get(q.id)) for q in questions)
            submission.max_score = quizzes.max_score(questions)
        db.add(submission)
        db.flush()  # need submission.id for the response rows
        _write_responses(db, form.id, submission.id, submitted, questions if is_quiz else None)
        db.commit()
        logger.info(f"{noun}_submitted", form_id=form.id, submission_id=submission.id)
        traffic.record(surface, "submit")
        if is_quiz:
            return _result(db, form, submission, raw_token)
        return FormSubmitAck(submission_id=submission.id, edit_token=raw_token)

    if is_quiz:

        @router.get("/by-token/{token}", response_model=QuizResultOut)
        def get_quiz_result(token: str, db: Session = Depends(get_db)) -> QuizResultOut:
            """The result again, later. Read-only on purpose: changing
            an answer after seeing the score is a second attempt, not a
            correction (``docs/design-quizzes.md`` part 3.4). There is
            no PUT on this path for a quiz."""
            sub = _submission_by_token(db, token)
            form = db.get(Form, sub.form_id)
            assert form is not None  # the token resolver already validated it
            return _result(db, form, sub, token)

    else:

        @router.get("/by-token/{token}", response_model=FormEditOut)
        def get_form_submission(token: str, db: Session = Depends(get_db)) -> FormEditOut:
            """Current values of a submission, for pre-filling the edit
            form. Gated by the secret token (the link)."""
            sub = _submission_by_token(db, token)
            return FormEditOut(
                display_name=sub.display_name,
                answers=_answers_for(db, sub.id),  # type: ignore[arg-type]
                link_recovered_at=sub.link_recovered_at,
            )

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
            submitted = _build_submitted(_form_questions(db, sub.form_id), data.answers)
            db.query(FormResponse).filter(FormResponse.submission_id == sub.id).delete()
            sub.display_name = data.display_name
            _write_responses(db, sub.form_id, sub.id, submitted, None)
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


router = build_router("survey", prefix="/api/v1/forms", tag="forms", surface="public_form", noun="form")
quiz_router = build_router("quiz", prefix="/api/v1/quizzes", tag="quizzes", surface="public_quiz", noun="quiz")
