"""Grading: the part of a quiz that a questionnaire does not have.

Everything else about a quiz lives in ``services/forms.py``, because
everything else about a quiz *is* a questionnaire (``docs/design-
quizzes.md``). This module holds the three things that are only true
when there is a right answer:

* ``grade`` — is this answer the right one, and what is it worth.
* ``validate_kinds`` / ``validate_keys`` — can this question be marked
  at all, checked when the organiser saves rather than when somebody
  submits.
* ``score_of`` / ``score_stats`` / ``correct_shares`` — the reads that
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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

# The kinds a quiz can ask. Both free-text kinds are out: no rule
# grades a paragraph, and an exact-match short answer is a quiz that
# turns on spelling rather than on knowing the answer. A question a
# quiz cannot mark is not a quiz question, so it is refused when the
# organiser saves rather than allowed and quietly worth nothing.
QUIZ_KINDS = frozenset({"rating", "number", "single_choice", "multi_choice"})


@dataclass(frozen=True, slots=True)
class QuizSummaryStats:
    """The marks on the organiser's summary page, read in one go."""

    average: float | None
    best: int | None
    out_of: int
    shares: dict[str, float]


def effective_points(question: Any) -> int:
    """What a question is worth. ``None`` on an incoming payload means
    the organiser did not say, which is one point: questions are worth
    the same until somebody decides otherwise."""
    points = getattr(question, "points", None)
    return 1 if points is None else int(points)


def max_score(questions: Sequence[Any]) -> int:
    """What a perfect run is worth."""
    return sum(q.points for q in questions if q.points > 0)


# What one answer earned, decided by the database.
#
# The marking rules, as SQL, and the same ones the module described in
# Python: a rating or a number is right within its tolerance window; a
# single choice is right when the ticks are exactly the key; a multiple
# choice pays part marks, ``(right - wrong) / right``, so one wrong tick
# cancels one right tick and ticking everything nets out at nothing.
# Negative is clamped, because a question cannot take away points earned
# elsewhere, and the share is floored, because a mark is a whole number.
#
# A question worth nothing earns nothing whatever the answer, which is
# every question on a questionnaire.
_EARNED_CTE = """
SELECT r.id AS response_id,
       r.submission_id,
       r.question_id,
       CASE
           WHEN q.points <= 0 THEN 0
           WHEN q.kind IN ('rating', 'number') THEN
               CASE
                   WHEN r.answer_int IS NOT NULL
                    AND q.correct_int IS NOT NULL
                    AND abs(r.answer_int - q.correct_int) <= coalesce(q.tolerance, 0)
                   THEN q.points ELSE 0
               END
           WHEN q.kind = 'single_choice' THEN
               CASE
                   WHEN coalesce(k.size, 0) > 0
                    AND coalesce(t.hits, 0) = k.size
                    AND coalesce(t.wrong, 0) = 0
                   THEN q.points ELSE 0
               END
           WHEN q.kind = 'multi_choice' THEN
               CASE
                   WHEN coalesce(k.size, 0) > 0 THEN
                       floor(
                           q.points
                           * greatest(0, (coalesce(t.hits, 0) - coalesce(t.wrong, 0))::numeric / k.size)
                       )::int
                   ELSE 0
               END
           ELSE 0
       END AS earned,
       q.points AS points
FROM form_responses r
JOIN form_questions q ON q.id = r.question_id
LEFT JOIN (
    SELECT question_id, count(*) AS size
    FROM form_question_options WHERE is_correct GROUP BY question_id
) k ON k.question_id = q.id
LEFT JOIN (
    SELECT c.response_id,
           count(*) FILTER (WHERE o.is_correct) AS hits,
           count(*) FILTER (WHERE NOT o.is_correct) AS wrong
    FROM form_response_choices c
    JOIN form_question_options o ON o.id = c.option_id
    GROUP BY c.response_id
) t ON t.response_id = r.id
WHERE r.form_id = :form_id
"""

# Every submission's score, including the ones that answered nothing:
# they played, and they scored zero.
_SCORES_SQL = text(
    f"""
WITH earned AS ({_EARNED_CTE})
SELECT s.id AS submission_id, coalesce(sum(e.earned), 0)::int AS score
FROM form_submissions s
LEFT JOIN earned e ON e.submission_id = s.id
WHERE s.form_id = :form_id
GROUP BY s.id
"""
)

# The organiser's summary in one round trip. The two halves are the
# same marks read at two grains, per player and per question, so they
# are one statement rather than two passes over the same rows.
_SUMMARY_SQL = text(
    f"""
WITH earned AS ({_EARNED_CTE}),
played AS (
    SELECT s.id, coalesce(sum(e.earned), 0)::int AS score
    FROM form_submissions s
    LEFT JOIN earned e ON e.submission_id = s.id
    WHERE s.form_id = :form_id
    GROUP BY s.id
),
shares AS (
    SELECT question_id,
           round(count(*) FILTER (WHERE earned >= points)::numeric / count(*), 2)::float AS share
    FROM earned
    WHERE points > 0
    GROUP BY question_id
)
SELECT (SELECT round(avg(score)::numeric, 1)::float FROM played) AS average,
       (SELECT max(score) FROM played) AS best,
       (SELECT coalesce(json_object_agg(question_id, share), '{{}}'::json) FROM shares) AS shares
"""
)


# What one person's answers earned, for the page that shows them their
# own marked quiz.
_EARNED_SQL = text(
    f"""
WITH earned AS ({_EARNED_CTE})
SELECT question_id, earned
FROM earned
WHERE submission_id = :submission_id
"""
)


def scores(db: Session, form_id: str) -> dict[str, int]:
    """Submission id to what it scored, for every submission."""
    return {row.submission_id: row.score for row in db.execute(_SCORES_SQL, {"form_id": form_id}).all()}


def earned_points(db: Session, form_id: str, submission_id: str) -> dict[str, int]:
    """Question id to what one submission's answer earned on it."""
    return {
        row.question_id: row.earned
        for row in db.execute(_EARNED_SQL, {"form_id": form_id, "submission_id": submission_id}).all()
    }


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
            # The key is which options are marked correct, so it cannot
            # name something that is not an option.
            marked = [o for o in q.options if o.is_correct]
            if not marked:
                raise bad("a scored question needs a correct answer.")
            if q.kind == "single_choice" and len(marked) != 1:
                raise bad("a single-choice question has exactly one correct option.")


def summary_stats(db: Session, form_id: str, questions: Sequence[Any]) -> QuizSummaryStats:
    """What the organiser's summary page says about the marks: the
    average and best scores, what a perfect run is worth, and the share
    of each scored question's answers that got full marks.

    Derived, like every other score here: re-weight a question and this
    moves with it, which is what an organiser means when they change
    the weight. Before anybody has played there is no average and no
    best, and no question has a share."""
    row = db.execute(_SUMMARY_SQL, {"form_id": form_id}).one()
    return QuizSummaryStats(
        average=row.average,
        best=row.best,
        out_of=max_score(questions),
        shares=row.shares or {},
    )
