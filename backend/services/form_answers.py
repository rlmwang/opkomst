"""The stored answers of one form, read once and grouped.

Three surfaces read every answer a form holds: a quiz marks them, a
kompas places them, and the CSV export writes them out. Each used to
carry its own copy of the same query, so a kompas results page loaded
the whole ``form_responses`` table twice and a quiz page three times.

**Core, not the ORM.** An answer row is read, folded into a score or a
coordinate, and dropped; nothing here is ever written back. Selecting
the six columns the folds actually touch skips the identity map and the
attribute instrumentation, which is the difference between hydrating
one object per answer and reading one tuple. On a form with a few
hundred submissions that is the largest single hydration in the app.

Writing an answer stays on the ORM, in ``services/forms``, where the
tenant write guard can see it.

The rows this hands back answer ``answer_int`` / ``answer_text`` /
``answer_choices`` / ``question_id`` / ``submission_id`` by attribute,
which is what ``quizzes.as_fields`` and ``compass.as_fields`` read, so
the folds are the same code against either shape.
"""

from typing import Any

from sqlalchemy import Text, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from ..models import FormResponse, FormResponseChoice

# Everything the folds touch, and nothing else. ``form_id`` is the
# filter rather than a field: every caller already knows which form it
# asked about.
COLUMNS = (
    FormResponse.id,
    FormResponse.submission_id,
    FormResponse.question_id,
    FormResponse.answer_int,
    FormResponse.answer_text,
    # The ticks, as option ids, gathered from the join. Aggregated here
    # rather than joined out, so one answer stays one row.
    func.coalesce(
        func.array_agg(FormResponseChoice.option_id).filter(FormResponseChoice.option_id.is_not(None)),
        func.cast(postgresql.array([]), postgresql.ARRAY(Text)),
    ).label("answer_choices"),
)


def by_submission(db: Session, form_id: str) -> dict[str, list[Any]]:
    """``submission_id -> that person's answers``. One query, because
    every caller places or marks all of them at once."""
    grouped: dict[str, list[Any]] = {}
    for row in db.execute(
        select(*COLUMNS)
        .outerjoin(FormResponseChoice, FormResponseChoice.response_id == FormResponse.id)
        .where(FormResponse.form_id == form_id)
        .group_by(FormResponse.id)
    ).all():
        grouped.setdefault(row.submission_id, []).append(row)
    return grouped


def by_question(db: Session, form_id: str, question_ids: list[str]) -> dict[str, list[Any]]:
    """``question_id -> the answers given to it``, for the questions
    asked about. Empty ``question_ids`` asks nothing and queries
    nothing."""
    if not question_ids:
        return {}
    grouped: dict[str, list[Any]] = {}
    for row in db.execute(
        select(*COLUMNS)
        .outerjoin(FormResponseChoice, FormResponseChoice.response_id == FormResponse.id)
        .where(FormResponse.form_id == form_id, FormResponse.question_id.in_(question_ids))
        .group_by(FormResponse.id)
    ).all():
        grouped.setdefault(row.question_id, []).append(row)
    return grouped
