"""Grading: the part of a quiz that a questionnaire does not have.

Everything else about a quiz lives in ``services/forms.py``, because
everything else about a quiz *is* a questionnaire (``docs/design-
quizzes.md``). This module holds the three things that are only true
when there is a right answer:

* ``grade`` — is this answer the right one, and what is it worth.
* ``validate_kinds`` / ``validate_keys`` — can this question be marked
  at all, checked when the organiser saves rather than when somebody
  submits.
* ``score_of`` / ``score_stats`` / ``correct_share`` — the reads that
  only a marked submission can produce.

Grading happens here and only here, from the stored key. The key is
never sent to a browser before the submit (``PublicQuestionOut``), so
a client-side score would be a client-side guess.

**Scores are derived, never stored.** What is kept is what somebody
answered; the score is that answer read against the quiz as it stands
now. So an organiser who fixes a wrong key or re-weights a question
sees every score correct itself, which is what they meant by editing,
and no two numbers on a page can disagree because there is only one
number and it is computed the same way everywhere.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import FormQuestion, FormResponse

# The kinds a quiz can ask. Both free-text kinds are out: no rule
# grades a paragraph, and an exact-match short answer is a quiz that
# turns on spelling rather than on knowing the answer. A question a
# quiz cannot mark is not a quiz question, so it is refused when the
# organiser saves rather than allowed and quietly worth nothing.
QUIZ_KINDS = frozenset({"rating", "number", "single_choice", "multi_choice"})


def is_correct(question: FormQuestion, fields: dict[str, Any]) -> bool:
    """Compare one stored-answer shape against the question's key.

    ``fields`` is what ``_build_submitted`` produced for this question:
    the same dict that is about to become a ``FormResponse`` row."""
    if question.kind in ("rating", "number"):
        answer = fields.get("answer_int")
        if answer is None or question.correct_int is None:
            return False
        return abs(answer - question.correct_int) <= (question.tolerance or 0)

    if question.kind in ("single_choice", "multi_choice"):
        chosen = fields.get("answer_choices") or []
        key = question.correct_choices or []
        if not key:
            return False
        return set(map(str, chosen)) == set(map(str, key))

    return False


def effective_points(question: Any) -> int:
    """What a question is worth. ``None`` on an incoming payload means
    the organiser did not say, which is one point: questions are worth
    the same until somebody decides otherwise."""
    points = getattr(question, "points", None)
    return 1 if points is None else int(points)


def multi_choice_share(question: FormQuestion, fields: dict[str, Any]) -> float:
    """What share of a multiple-choice question's points an answer
    earns, between 0 and 1.

    ``(right ticks - wrong ticks) / right options``: one wrong tick
    cancels one right tick, so a pick is worth the same whichever way it
    goes. Two of two right is full marks; two right and one wrong is
    half; ticking everything nets out at nothing.

    Counting each pick equally is the point. Scaling the penalty by how
    many wrong options there were instead would make a wrong tick cheap
    on a question with many of them and expensive on a question with
    one, for the same mistake.

    Negative is clamped to zero: a quiz question cannot take points off
    a score somebody earned elsewhere."""
    key = {str(c) for c in (question.correct_choices or [])}
    if not key:
        return 0.0
    chosen = {str(c) for c in (fields.get("answer_choices") or [])}
    hits = len(chosen & key)
    wrong = len(chosen - key)
    return max(0.0, (hits - wrong) / len(key))


def grade(question: FormQuestion, fields: dict[str, Any] | None) -> int:
    """Points earned by one answer. An unanswered question and a wrong
    one are both worth nothing, which is the same thing from the
    score's point of view.

    Multiple choice is the one kind that pays part marks
    (``multi_choice_share``), rounded down. Every other kind is right or
    it is not."""
    if question.points <= 0 or fields is None:
        return 0
    if question.kind == "multi_choice":
        return int(question.points * multi_choice_share(question, fields))
    return question.points if is_correct(question, fields) else 0


def max_score(questions: list[FormQuestion]) -> int:
    """What a perfect run is worth."""
    return sum(q.points for q in questions if q.points > 0)


def _as_fields(row: FormResponse) -> dict[str, Any]:
    """A stored answer row in the shape ``grade`` compares against."""
    return {
        "answer_int": row.answer_int,
        "answer_text": row.answer_text,
        "answer_choices": list(row.answer_choices) if row.answer_choices else None,
    }


def score_of(questions: list[FormQuestion], rows: list[FormResponse]) -> int:
    """One submission's score: every stored answer marked against the
    quiz as it stands now."""
    by_id = {q.id: q for q in questions}
    return sum(grade(by_id[r.question_id], _as_fields(r)) for r in rows if r.question_id in by_id)


def rows_by_submission(db: Session, form_id: str) -> dict[str, list[FormResponse]]:
    """Every stored answer for this quiz, grouped by who gave it. One
    query, because the organiser's page marks every submission."""
    grouped: dict[str, list[FormResponse]] = {}
    for row in db.query(FormResponse).filter(FormResponse.form_id == form_id).all():
        grouped.setdefault(row.submission_id, []).append(row)
    return grouped


def validate_kinds(questions: list[Any]) -> None:
    """A quiz asks only what it can mark. Raises HTTPException(400) on
    a free-text question, with the reason, so an organiser reading the
    message knows why rather than finding the question silently worth
    nothing later."""
    for idx, q in enumerate(questions, start=1):
        if q.kind not in QUIZ_KINDS:
            raise HTTPException(
                status_code=400,
                detail=f"Question {idx}: a quiz cannot mark an open answer. Use a choice, a number or a rating.",
            )


def validate_keys(questions: list[Any]) -> None:
    """A scored question needs a key that its kind can use, checked when
    the quiz is saved.

    The alternative is discovering it at submit time, when the person
    who can fix it is not the person looking at the screen. Raises
    HTTPException(400) so the message reaches the organiser verbatim,
    the same way the per-kind question validation already does."""
    for idx, q in enumerate(questions, start=1):
        if effective_points(q) <= 0:
            continue

        def bad(reason: str, idx: int = idx) -> HTTPException:
            return HTTPException(status_code=400, detail=f"Question {idx}: {reason}")

        if q.kind in ("rating", "number"):
            if q.correct_int is None:
                raise bad("a scored question needs a correct answer.")
            if q.kind == "rating" and not 1 <= q.correct_int <= 5:
                raise bad("the correct answer has to be on the 1 to 5 scale.")
            if q.kind == "number":
                if q.min_value is not None and q.correct_int < q.min_value:
                    raise bad("the correct answer is below the lowest allowed number.")
                if q.max_value is not None and q.correct_int > q.max_value:
                    raise bad("the correct answer is above the highest allowed number.")
        elif q.kind in ("single_choice", "multi_choice"):
            key = [c.strip() for c in (q.correct_choices or []) if c.strip()]
            options = [o.strip() for o in q.options if o.strip()]
            if not key:
                raise bad("a scored question needs a correct answer.")
            if any(c not in options for c in key):
                raise bad("the correct answer has to be one of the options.")
            if q.kind == "single_choice" and len(key) != 1:
                raise bad("a single-choice question has exactly one correct option.")


def score_stats(
    db: Session,
    form_id: str,
    questions: list[FormQuestion],
) -> tuple[float | None, int | None, int | None]:
    """Average score, best score, and what a perfect run is worth. All
    three are None before anybody has played.

    Derived, like every other score here: re-weight a question and this
    moves with it, which is what an organiser means when they change
    the weight."""
    grouped = rows_by_submission(db, form_id)
    if not grouped:
        return None, None, None
    scores = [score_of(questions, rows) for rows in grouped.values()]
    return round(sum(scores) / len(scores), 1), max(scores), max_score(questions)


def correct_share(db: Session, form_id: str, question: FormQuestion) -> float | None:
    """The share of answers to this question that earned full marks.
    None for a question nobody scored, which includes every question on
    a survey."""
    if question.points <= 0:
        return None
    rows = db.query(FormResponse).filter(FormResponse.form_id == form_id, FormResponse.question_id == question.id).all()
    if not rows:
        return None
    # Full marks, not part marks: the question this answers is "how
    # many of them got it", and half a multiple-choice answer is not
    # getting it.
    return round(sum(1 for r in rows if grade(question, _as_fields(r)) >= question.points) / len(rows), 2)
