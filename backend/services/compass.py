"""Where an answer puts somebody: the part of a kompas that a
questionnaire does not have.

Everything else about a kompas lives in ``services/forms.py``, because
everything else about a kompas *is* a questionnaire
(``docs/design-kompas.md``). This module holds the three things that
are only true when an answer has a direction:

* ``contribution`` / ``position_of`` / ``positions`` — what one answer
  is worth, where one submission lands, and where everybody lands.
* ``validate_axes`` / ``validate_questions`` — can this kompas place
  anybody at all, checked when the organiser saves rather than when
  somebody submits.
* ``axis_stats`` — the one aggregate a kompas has that a questionnaire
  cannot: how the room sits on each axis.

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
from sqlalchemy.orm import Session

from ..models import CompassAxis, FormQuestion, FormResponse

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


def contribution(question: FormQuestion, fields: dict[str, Any] | None) -> tuple[str, float] | None:
    """What one answer is worth: an axis, and a value in [-1, 1].

    ``None`` when the answer says nothing about either axis, which
    covers an unanswered question, a question with no pole on it, and a
    kind a kompas does not ask.

    ``fields`` is the stored-answer shape ``_build_submitted`` produces,
    the same dict ``services/quizzes.grade`` compares against."""
    if fields is None:
        return None

    if question.kind == "rating":
        if not question.pole or question.pole not in POLES:
            return None
        answer = fields.get("answer_int")
        if answer is None:
            return None
        axis, direction = split_pole(question.pole)
        return axis, _round(((answer - RATING_MIDPOINT) / RATING_HALF_RANGE) * direction)

    if question.kind == "single_choice":
        chosen = fields.get("answer_choices") or []
        if len(chosen) != 1:
            return None
        poles = question.option_poles or []
        options = question.options or []
        try:
            index = options.index(str(chosen[0]))
        except ValueError:
            return None
        if index >= len(poles) or poles[index] not in POLES:
            return None
        axis, direction = split_pole(poles[index])
        return axis, float(direction)

    return None


def as_fields(row: FormResponse) -> dict[str, Any]:
    """A stored answer row in the shape ``contribution`` reads."""
    return {
        "answer_int": row.answer_int,
        "answer_choices": list(row.answer_choices) if row.answer_choices else None,
    }


def position_of(questions: list[FormQuestion], rows: list[FormResponse]) -> Position:
    """One submission's place on the map: the mean of its answers'
    contributions, per axis.

    A mean rather than a sum, because a kompas need not be balanced.
    Eight questions on one axis and three on the other still read on
    the same scale, and each coordinate answers "how far toward this
    side were your answers on this subject" rather than "how many of
    them were there"."""
    by_id = {q.id: q for q in questions}
    buckets: dict[str, list[float]] = {"x": [], "y": []}
    for row in rows:
        question = by_id.get(row.question_id)
        if question is None:
            continue
        found = contribution(question, as_fields(row))
        if found is None:
            continue
        axis, value = found
        buckets[axis].append(value)
    return Position(
        x=_round(sum(buckets["x"]) / len(buckets["x"])) if buckets["x"] else 0.0,
        y=_round(sum(buckets["y"]) / len(buckets["y"])) if buckets["y"] else 0.0,
        counted_x=len(buckets["x"]),
        counted_y=len(buckets["y"]),
    )


def rows_by_submission(db: Session, form_id: str) -> dict[str, list[FormResponse]]:
    """Every stored answer for this kompas, grouped by who gave it. One
    query, because both the organiser's page and every respondent's map
    place all of them at once."""
    grouped: dict[str, list[FormResponse]] = {}
    for row in db.query(FormResponse).filter(FormResponse.form_id == form_id).all():
        grouped.setdefault(row.submission_id, []).append(row)
    return grouped


def positions(db: Session, questions: list[FormQuestion], form_id: str) -> dict[str, Position]:
    """Submission id to place on the map, for every submission."""
    return {sid: position_of(questions, rows) for sid, rows in rows_by_submission(db, form_id).items()}


def axes_of(db: Session, form_id: str) -> list[CompassAxis]:
    """The two axis rows, ``x`` first. Empty on a form that is not a
    kompas, which is how every caller tells."""
    rows = db.query(CompassAxis).filter(CompassAxis.form_id == form_id).all()
    return sorted(rows, key=lambda a: a.axis)


def axis_stats(places: list[Position], axis: str) -> tuple[float, float, float] | None:
    """The room on one axis: mean, lowest, highest. ``None`` before
    anybody has filled it in."""
    if not places:
        return None
    values = [p.value(axis) for p in places]
    return _round(sum(values) / len(values)), min(values), max(values)


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

        # Against the payload's own options, not the cleaned list: the
        # two arrive parallel and are filtered together on write, so a
        # length that disagrees here is a client that built them apart.
        options = list(q.options)
        poles = list(q.option_poles or [])
        if len(poles) != len(options):
            raise _bad(f"Question {idx}: pick a side of an axis for every answer.")
        for option, pole in zip(options, poles, strict=True):
            if not option.strip():
                continue
            if not (pole or "").strip():
                raise _bad(f"Question {idx}: pick a side of an axis for every answer.")
            if pole not in POLES:
                raise _bad(f"Question {idx}: that answer belongs to an axis that does not exist.")
            used.add(split_pole(pole)[0])

    for a in axes:
        if a.axis not in used:
            name = (a.name or a.axis).strip()
            raise _bad(f"Nobody can move on axis {name}: no question belongs to it.")
