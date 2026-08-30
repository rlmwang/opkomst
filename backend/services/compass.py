"""Where an answer puts somebody: the part of a kompas that a
questionnaire does not have.

Everything else about a kompas lives in ``services/forms.py``, because
everything else about a kompas *is* a questionnaire
(``docs/design-kompas.md``). This module holds the three things that
are only true when an answer has a direction:

* ``contributions`` / ``positions`` — what one answer
  is worth, where one submission lands, and where everybody lands.
* ``validate_axes`` / ``validate_questions`` — can this kompas place
  anybody at all, checked when the organiser saves rather than when
  somebody submits.
* ``axis_stats`` — the one aggregate a kompas has that a questionnaire
  cannot: how the room sits on each axis, and how sure that is.

**Positions are derived, never stored.** What is kept is what somebody
answered; the position is that answer read against the kompas as it
stands now. So an organiser who moves an option from one side to the
other sees every dot move with it, which is what they meant by editing,
and no two pictures on a page can disagree because there is only one
computation and every caller runs it.

The arithmetic comes from ``../stemwijzer``'s ``compute_axes``: a
point is the mean of ``answer_value * direction`` per axis. A rating
supplies the answer value (a 5 is 1.0, a 1 is -1.0, a 3 is 0.0) and the
statement supplies the direction; a choice has no degrees, so its
chosen option supplies both and lands on one of the two endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import CompassAxis

# The kinds a kompas can ask. A rating is the classic compass question:
# a statement, a five-point scale, one direction. A choice is the
# question a scale cannot ask, where the answers are alternatives
# rather than degrees. Nothing else: a multi-choice answer pulls three
# ways at once, a number has no direction, and no rule points a
# paragraph anywhere.
COMPASS_KINDS: Final[frozenset[str]] = frozenset({"rating", "single_choice"})

# The four tokens a pole can be: an axis, and a direction along it.
AXES: Final[tuple[str, str]] = ("x", "y")
SIDES: Final[tuple[str, str]] = ("low", "high")
POLES: Final[frozenset[str]] = frozenset(f"{axis}_{side}" for axis in AXES for side in SIDES)

# What a rating answer is worth before the direction is applied:
# 1 -> -1.0, 2 -> -0.5, 3 -> 0.0, 4 -> +0.5, 5 -> +1.0. The middle of
# the scale is worth nothing and still counts, which is what makes it
# different from not answering at all.
RATING_MIDPOINT: Final[int] = 3
RATING_HALF_RANGE: Final[float] = 2.0


def _round(value: float) -> float:
    """Three decimals, and never negative zero. A 3 on a scale poled
    the low way multiplies out to ``-0.0``, which is the same number and
    a different word: it reaches a screen as "-0" and reads as a
    direction nobody took."""
    rounded = round(value, 3)
    return rounded if rounded else 0.0


def split_pole(pole: str) -> tuple[str, int]:
    """``"x_low"`` into the axis and the direction, ``-1`` or ``+1``."""
    axis, _, side = pole.partition("_")
    return axis, 1 if side == "high" else -1


@dataclass(frozen=True)
class Position:
    """Where one submission sits, and on how much. ``counted_x`` is the
    number of answers that had anything to say about ``x``: zero means
    the coordinate is 0.0 because nobody said anything, which is a
    different sentence from 0.0 because the answers balanced."""

    x: float
    y: float
    counted_x: int
    counted_y: int

    @property
    def counted(self) -> dict[str, int]:
        return {"x": self.counted_x, "y": self.counted_y}

    def value(self, axis: str) -> float:
        return self.x if axis == "x" else self.y


# What one answer is worth: an axis, and a value in [-1, 1].
#
# The three rules the page describes, as SQL. A rating poles the
# statement, so a 5 is all the way toward that side and a 1 all the way
# to the other. A choice poles each option and lands on its own end, and
# only a single pick counts: a question answered with two ticks points
# two ways at once, which is not a direction. An answer that says
# nothing about either axis contributes no row at all, which is how a
# skipped question stops counting rather than counting as a zero.
_CONTRIBUTION_CTE = """
SELECT r.submission_id,
       r.question_id,
       split_part(q.pole, '_', 1) AS axis,
       ((r.answer_int - :midpoint)::numeric / (:half_range)::numeric)
           * CASE WHEN split_part(q.pole, '_', 2) = 'high' THEN 1 ELSE -1 END AS value
FROM form_responses r
JOIN form_questions q ON q.id = r.question_id
WHERE r.form_id = :form_id
  AND q.kind = 'rating'
  AND q.pole = ANY(:poles)
  AND r.answer_int IS NOT NULL

UNION ALL

SELECT r.submission_id,
       r.question_id,
       split_part(o.pole, '_', 1) AS axis,
       (CASE WHEN split_part(o.pole, '_', 2) = 'high' THEN 1 ELSE -1 END)::numeric AS value
FROM form_responses r
JOIN form_questions q ON q.id = r.question_id
JOIN form_response_choices c ON c.response_id = r.id
JOIN form_question_options o ON o.id = c.option_id
WHERE r.form_id = :form_id
  AND q.kind = 'single_choice'
  AND o.pole = ANY(:poles)
  AND (SELECT count(*) FROM form_response_choices c2 WHERE c2.response_id = r.id) = 1
"""

# A position is the mean per axis, so an unbalanced kompas still reads
# on one scale: eight questions on one axis and three on the other
# answer "how far toward this side were you", not "how many were there".
#
# Numeric rather than float, so a coordinate cannot come back as
# ``-0.0``: a 3 on a scale poled the low way multiplied out to negative
# zero, which is the same number and a different word, and reached a
# screen reading as a direction nobody took.
PLACES_SQL = f"""
WITH contribution AS ({_CONTRIBUTION_CTE})
SELECT s.id AS submission_id,
       coalesce(round(avg(k.value) FILTER (WHERE k.axis = 'x'), 3), 0)::float AS x,
       coalesce(round(avg(k.value) FILTER (WHERE k.axis = 'y'), 3), 0)::float AS y,
       count(*) FILTER (WHERE k.axis = 'x')::int AS counted_x,
       count(*) FILTER (WHERE k.axis = 'y')::int AS counted_y
FROM form_submissions s
LEFT JOIN contribution k ON k.submission_id = s.id
WHERE s.form_id = :form_id
  AND (cast(:submission_id AS text) IS NULL OR s.id = :submission_id)
GROUP BY s.id
"""

# The same statement as a string, so the CSV export can nest it as a
# CTE and put a kompas' two derived columns beside the answers that
# made them. One place decides where somebody sits.
_POSITIONS_SQL = text(PLACES_SQL)

# The same rows, unaggregated: what each answer of one submission was
# worth, for the result page that says "this moved you 0.5 toward
# Rechts".
_CONTRIBUTIONS_SQL = text(
    f"""
SELECT question_id, axis, round(value, 3)::float AS value
FROM ({_CONTRIBUTION_CTE}) k
WHERE k.submission_id = :submission_id
"""
)


def params(form_id: str, submission_id: str | None = None) -> dict[str, Any]:
    """The rules the statements are parameterised on, so the numbers
    that define the scale live in one place and Python and SQL cannot
    disagree about them."""
    return {
        "form_id": form_id,
        "submission_id": submission_id,
        "midpoint": RATING_MIDPOINT,
        "half_range": RATING_HALF_RANGE,
        "poles": sorted(POLES),
    }


def positions(db: Session, form_id: str, submission_id: str | None = None) -> dict[str, Position]:
    """Submission id to place on the map. One statement: nothing is read
    into Python to be averaged there. Narrowed to one submission for the
    result page that shows a person their own dot."""
    return {
        row.submission_id: Position(x=row.x, y=row.y, counted_x=row.counted_x, counted_y=row.counted_y)
        for row in db.execute(_POSITIONS_SQL, params(form_id, submission_id)).all()
    }


def contributions(db: Session, form_id: str, submission_id: str) -> dict[str, tuple[str, float]]:
    """Question id to the axis one submission's answer moved, and how
    far. Absent for a question that said nothing about either axis."""
    return {
        row.question_id: (row.axis, row.value)
        for row in db.execute(_CONTRIBUTIONS_SQL, params(form_id, submission_id)).all()
    }


def axes_of(db: Session, form_id: str) -> list[Any]:
    """The two axis rows, ``x`` first. Empty on a form that is not a
    kompas, which is how every caller tells."""
    rows = db.execute(select(*CompassAxis.__table__.c).where(CompassAxis.form_id == form_id)).all()
    return sorted(rows, key=lambda a: a.axis)


# Where the room sits on each axis: the mean, and the 95% confidence
# interval around it.
#
# The interval, not the range. The range is a picture of the two most
# extreme people in the room and it widens as more of them arrive,
# which reads as the answer getting less certain the more of it you
# have. What an organiser is actually asking is "where does this room
# sit, and how sure is that", and the interval narrows with the count
# the way an answer should.
#
# The critical values are two-sided 95% Student's t by degrees of
# freedom, written out as a table the statement joins. The interval is
# about a mean of a handful of numbers, so the normal approximation is
# wrong exactly where a kompas lives: at n = 3 it is out by a factor of
# two. Beyond 30 the two agree to the second decimal and 1.96 takes
# over.
#
# One respondent has a mean and no interval to speak of, so both ends
# are the mean itself: a point, which is the honest drawing of it.
# ``stddev_samp`` is null at n = 1, and coalescing the half-width to
# zero says the same thing. The ends are clamped to [-1, 1] because the
# axis has no outside.
_AXIS_STATS_SQL = text(
    f"""
WITH contribution AS ({_CONTRIBUTION_CTE}),
place AS (
    SELECT s.id,
           coalesce(avg(k.value) FILTER (WHERE k.axis = 'x'), 0) AS x,
           coalesce(avg(k.value) FILTER (WHERE k.axis = 'y'), 0) AS y
    FROM form_submissions s
    LEFT JOIN contribution k ON k.submission_id = s.id
    WHERE s.form_id = :form_id
    GROUP BY s.id
),
value AS (
    SELECT 'x' AS axis, x AS v FROM place
    UNION ALL
    SELECT 'y' AS axis, y AS v FROM place
),
room AS (
    SELECT axis, count(*) AS n, avg(v) AS mean, stddev_samp(v) AS sd
    FROM value GROUP BY axis
),
t95 (df, crit) AS (
    VALUES (1, 12.706), (2, 4.303), (3, 3.182), (4, 2.776), (5, 2.571),
           (6, 2.447), (7, 2.365), (8, 2.306), (9, 2.262), (10, 2.228),
           (11, 2.201), (12, 2.179), (13, 2.160), (14, 2.145), (15, 2.131),
           (16, 2.120), (17, 2.110), (18, 2.101), (19, 2.093), (20, 2.086),
           (21, 2.080), (22, 2.074), (23, 2.069), (24, 2.064), (25, 2.060),
           (26, 2.056), (27, 2.052), (28, 2.048), (29, 2.045), (30, 2.042)
)
SELECT room.axis,
       round(room.mean, 3)::float AS average,
       round(greatest(-1, room.mean - half.width), 3)::float AS ci_low,
       round(least(1, room.mean + half.width), 3)::float AS ci_high
FROM room
LEFT JOIN t95 ON t95.df = room.n - 1
CROSS JOIN LATERAL (
    SELECT coalesce(coalesce(t95.crit, 1.96)::numeric * room.sd / sqrt(room.n)::numeric, 0) AS width
) half
"""
)


def axis_stats(db: Session, form_id: str) -> dict[str, tuple[float, float, float]]:
    """Axis name to the room's mean and the two ends of the interval
    around it. Empty before anybody has filled the kompas in."""
    return {
        row.axis: (row.average, row.ci_low, row.ci_high) for row in db.execute(_AXIS_STATS_SQL, params(form_id)).all()
    }


# --- What the organiser is refused ------------------------------------


def _bad(reason: str) -> HTTPException:
    return HTTPException(status_code=400, detail=reason)


def validate_axes(axes: list[Any]) -> None:
    """A kompas has two named axes with four named sides. Checked when
    the organiser saves, because the result screen builds sentences out
    of these words and an unnamed side is a sentence with a hole."""
    if len(axes) != 2 or {a.axis for a in axes} != set(AXES):
        raise _bad("A kompas has exactly two axes, x and y.")
    for a in axes:
        if not (a.name or "").strip():
            raise _bad(f"Give axis {a.axis.upper()} a name.")
        if not (a.low_name or "").strip() or not (a.high_name or "").strip():
            raise _bad(f"Give both sides of axis {a.name.strip()} a name.")


def validate_questions(questions: list[Any], axes: list[Any]) -> None:
    """Every question can move somebody, and every axis can be moved
    on. Raises HTTPException(400) naming the question, so an organiser
    reading the message knows which one rather than finding out on the
    night.

    Any of the four sides may go unused: a kompas whose questions all
    push one way is the organiser's choice, and sometimes the honest
    one. An axis that nothing touches is not a choice, it is a
    half-written kompas."""
    used: set[str] = set()
    for idx, q in enumerate(questions, start=1):
        if q.kind not in COMPASS_KINDS:
            raise _bad(f"Question {idx}: a kompas asks only statements and multiple-choice questions.")
        if q.kind == "rating":
            pole = (q.pole or "").strip()
            if not pole:
                raise _bad(f"Question {idx}: pick which side a 5 on this scale means.")
            if pole not in POLES:
                raise _bad(f"Question {idx}: that side belongs to an axis that does not exist.")
            used.add(split_pole(pole)[0])
            continue

        # Each option carries its own side, so there is no second list
        # to fall out of step with this one.
        for option in q.options:
            if not option.label.strip():
                continue
            pole = (option.pole or "").strip()
            if not pole:
                raise _bad(f"Question {idx}: pick a side of an axis for every answer.")
            if pole not in POLES:
                raise _bad(f"Question {idx}: that answer belongs to an axis that does not exist.")
            used.add(split_pole(pole)[0])

    for a in axes:
        if a.axis not in used:
            name = (a.name or a.axis).strip()
            raise _bad(f"Nobody can move on axis {name}: no question belongs to it.")
