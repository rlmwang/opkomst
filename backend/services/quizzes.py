"""Grading: the part of a quiz that a questionnaire does not have.

Everything else about a quiz lives in ``services/forms.py``, because
everything else about a quiz *is* a questionnaire (``docs/design-
quizzes.md``). This module holds the three things that are only true
when there is a right answer:

* ``grade`` — is this answer the right one, and what is it worth.
* ``validate_keys`` — is this question's key usable at all, checked
  when the organiser saves rather than when a respondent submits.
* ``score_stats`` / ``correct_share`` — the organiser-side reads that
  only a graded submission can produce.

Grading happens here and only here, from the stored key. The key is
never sent to a browser before the submit (``PublicQuestionOut``), so
a client-side score would be a client-side guess.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import FormQuestion, FormResponse, FormSubmission

# The kind that can be asked in a quiz and never scored. No rule grades
# a paragraph, and inventing manual grading to allow one is a different
# feature; a ``text`` question is worth 0 and the editor says so.
UNSCORABLE_KINDS = frozenset({"text"})

_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Case and spacing are not the answer. "Den Haag" and "den  haag"
    are the same guess, and a respondent typing on a phone should not
    lose a point to a capital."""
    return _WHITESPACE.sub(" ", text.strip()).casefold()


def is_correct(question: FormQuestion, fields: dict[str, Any]) -> bool:
    """Compare one stored-answer shape against the question's key.

    ``fields`` is what ``_build_submitted`` produced for this question:
    the same dict that is about to become a ``FormResponse`` row."""
    if question.kind in ("rating", "number"):
        answer = fields.get("answer_int")
        if answer is None or question.correct_int is None:
            return False
        return abs(answer - question.correct_int) <= (question.tolerance or 0)

    if question.kind == "short_text":
        answer = fields.get("answer_text")
        if not answer or not question.correct_text:
            return False
        return _normalise(str(answer)) == _normalise(question.correct_text)

    if question.kind in ("single_choice", "multi_choice"):
        chosen = fields.get("answer_choices") or []
        key = question.correct_choices or []
        if not key:
            return False
        # Exact set, no partial credit. Partial credit needs a rule for
        # wrong extras (does picking all five options score three out of
        # three?) and every rule for that is arguable; this one nobody
        # has to explain.
        return set(map(str, chosen)) == set(map(str, key))

    return False


def grade(question: FormQuestion, fields: dict[str, Any] | None) -> int:
    """Points earned by one answer. An unanswered optional question and
    a wrong answer are both worth nothing, which is the same thing from
    the score's point of view."""
    if question.points <= 0 or fields is None:
        return 0
    return question.points if is_correct(question, fields) else 0


def max_score(questions: list[FormQuestion]) -> int:
    """What a perfect run is worth right now. Stored on the submission
    at submit time, because this number moves when the organiser edits
    the quiz and an old score has to stay readable."""
    return sum(q.points for q in questions if q.points > 0)


def validate_keys(questions: list[Any]) -> None:
    """A scored question needs a key that its kind can use, checked when
    the quiz is saved.

    The alternative is discovering it at submit time, when the person
    who can fix it is not the person looking at the screen. Raises
    HTTPException(400) so the message reaches the organiser verbatim,
    the same way the per-kind question validation already does."""
    for idx, q in enumerate(questions, start=1):
        if q.kind in UNSCORABLE_KINDS or q.points <= 0:
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
        elif q.kind == "short_text":
            if not (q.correct_text or "").strip():
                raise bad("a scored question needs a correct answer.")
        elif q.kind in ("single_choice", "multi_choice"):
            key = [c.strip() for c in (q.correct_choices or []) if c.strip()]
            options = [o.strip() for o in q.options if o.strip()]
            if not key:
                raise bad("a scored question needs a correct answer.")
            if any(c not in options for c in key):
                raise bad("the correct answer has to be one of the options.")
            if q.kind == "single_choice" and len(key) != 1:
                raise bad("a single-choice question has exactly one correct option.")


def score_stats(db: Session, form_id: str) -> tuple[float | None, int | None, int | None]:
    """Average score, best score, and the total the most recent taker
    was scored out of. All three are None before anybody has taken it.

    The total comes from the newest submission rather than from the
    questions as they stand now, so it agrees with the scores beside
    it even after the quiz has been edited."""
    row = (
        db.query(
            func.avg(FormSubmission.score),
            func.max(FormSubmission.score),
        )
        .filter(FormSubmission.form_id == form_id, FormSubmission.score.is_not(None))
        .one()
    )
    average, best = row
    if average is None:
        return None, None, None
    newest = (
        db.query(FormSubmission.max_score)
        .filter(FormSubmission.form_id == form_id, FormSubmission.max_score.is_not(None))
        .order_by(FormSubmission.created_at.desc())
        .first()
    )
    return round(float(average), 1), int(best), (int(newest[0]) if newest else None)


def correct_share(db: Session, form_id: str, question: FormQuestion) -> float | None:
    """The share of answers to this question that earned full marks.
    None for a question nobody scored, which includes every question on
    a survey."""
    if question.points <= 0:
        return None
    rows = (
        db.query(FormResponse.awarded)
        .filter(
            FormResponse.form_id == form_id,
            FormResponse.question_id == question.id,
            FormResponse.awarded.is_not(None),
        )
        .all()
    )
    if not rows:
        return None
    return round(sum(1 for (a,) in rows if a >= question.points) / len(rows), 2)
