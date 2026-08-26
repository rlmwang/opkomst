"""a quiz is a form with a key

The quiz half of the shared tables (``docs/design-quizzes.md`` part
1.2). Everything here is null or zero on a survey:

* ``form_questions`` gains what a correct answer is worth and what the
  correct answer is, one column per kind-shape plus a tolerance that
  widens a number's key into a range;
* ``form_submissions`` gains the score and the total it was out of,
  stored rather than computed because an organiser can edit the quiz
  afterwards and an old score has to stay readable;
* ``form_responses`` gains what each answer earned, for the same reason
  one level down;
* ``forms`` gains whether the result screen names the right answers.

Revision ID: 9892ae52f22f
Revises: 09232e4b5fae
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9892ae52f22f"
down_revision: str | None = "09232e4b5fae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("forms", sa.Column("reveal_answers", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("form_questions", sa.Column("points", sa.Integer(), server_default="0", nullable=False))
    op.add_column("form_questions", sa.Column("correct_int", sa.Integer(), nullable=True))
    op.add_column("form_questions", sa.Column("correct_text", sa.Text(), nullable=True))
    op.add_column("form_questions", sa.Column("correct_choices", sa.JSON(), nullable=True))
    op.add_column("form_questions", sa.Column("tolerance", sa.Integer(), nullable=True))
    op.add_column("form_submissions", sa.Column("score", sa.Integer(), nullable=True))
    op.add_column("form_submissions", sa.Column("max_score", sa.Integer(), nullable=True))
    op.add_column("form_responses", sa.Column("awarded", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("form_responses", "awarded")
    op.drop_column("form_submissions", "max_score")
    op.drop_column("form_submissions", "score")
    op.drop_column("form_questions", "tolerance")
    op.drop_column("form_questions", "correct_choices")
    op.drop_column("form_questions", "correct_text")
    op.drop_column("form_questions", "correct_int")
    op.drop_column("form_questions", "points")
    op.drop_column("forms", "reveal_answers")
