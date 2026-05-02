"""The five fixed feedback questions, as a Python constant.

These are app-level constants. Every install carries the same
five questions, by deliberate design — see ``CLAUDE.md`` rule
"the point of the standardisation is to reduce organiser
workload and keep stats comparable across events." There is no
per-event customisation, no admin tool to edit them, no public
API to mutate them. They have all the properties of source-code
constants, so they live in source code: no DB table, no seed
hook, no migration to backfill them.

A ``FeedbackResponse`` row references a question by ``key``
(``"q1_overall"`` etc.). The keys are stable for the lifetime of
the app — renaming one would orphan every existing response, so
treat them like enum values.

Adding a question:

* Append a new ``FeedbackQuestion`` to ``QUESTIONS`` with the
  next ordinal.
* Add the i18n strings under ``feedback.questions.<key>`` in
  ``frontend/src/locales/{nl,en}.json``.
* The new question is live as soon as the build deploys; no
  data migration runs.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class FeedbackQuestion:
    """One question. ``key`` is the stable identifier — used as
    both the API id and the i18n key for the prompt + labels.
    ``ordinal`` drives display order. ``kind`` tells the frontend
    which input to render and the server which answer column to
    persist into."""

    key: str
    ordinal: int
    kind: Literal["rating", "text"]
    required: bool


QUESTIONS: tuple[FeedbackQuestion, ...] = (
    FeedbackQuestion(key="q1_overall", ordinal=1, kind="rating", required=True),
    FeedbackQuestion(key="q2_recommend", ordinal=2, kind="rating", required=True),
    FeedbackQuestion(key="q3_welcome", ordinal=3, kind="rating", required=True),
    FeedbackQuestion(key="q4_better", ordinal=4, kind="text", required=False),
    FeedbackQuestion(key="q5_anything_else", ordinal=5, kind="text", required=False),
)

BY_KEY: dict[str, FeedbackQuestion] = {q.key: q for q in QUESTIONS}
