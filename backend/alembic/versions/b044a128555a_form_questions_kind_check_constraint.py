"""form_questions kind CHECK constraint

Revision ID: b044a128555a
Revises: 85f09654b16b
Create Date: 2026-06-13 20:23:02.520678
"""

from collections.abc import Sequence

from alembic import op


revision: str = 'b044a128555a'
down_revision: str | None = '85f09654b16b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Alembic does not autodetect CHECK constraints; this revision is
# hand-written. The kind vocabulary is the ``QuestionKind`` literal
# in ``backend/schemas/forms.py`` — keep the two in sync.
_KINDS = "('rating', 'text', 'short_text', 'single_choice', 'multi_choice')"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_form_questions_kind",
        "form_questions",
        f"kind IN {_KINDS}",
    )


def downgrade() -> None:
    op.drop_constraint("ck_form_questions_kind", "form_questions", type_="check")
