"""number question kind

A sixth question kind, ``number``, with the three columns only it
uses. The kind vocabulary lives in a CHECK constraint that autogenerate
does not diff, so the drop-and-recreate is written by hand: without it
the new kind is rejected by the database while passing every layer
above it.

Revision ID: e80bd732f041
Revises: 570e0e090c01
Create Date: 2026-08-26 17:47:38.756776
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e80bd732f041"
down_revision: str | None = "570e0e090c01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS_BEFORE = "kind IN ('rating', 'text', 'short_text', 'single_choice', 'multi_choice')"
_KINDS_AFTER = "kind IN ('rating', 'text', 'short_text', 'single_choice', 'multi_choice', 'number')"


def upgrade() -> None:
    op.add_column("form_questions", sa.Column("min_value", sa.Integer(), nullable=True))
    op.add_column("form_questions", sa.Column("max_value", sa.Integer(), nullable=True))
    op.add_column("form_questions", sa.Column("unit", sa.Text(), nullable=True))
    op.drop_constraint("ck_form_questions_kind", "form_questions", type_="check")
    op.create_check_constraint("ck_form_questions_kind", "form_questions", _KINDS_AFTER)


def downgrade() -> None:
    # Any ``number`` question would violate the narrower constraint, so
    # they go first. Dropping the columns loses their configuration
    # either way; deleting the rows is what makes the constraint
    # re-creatable rather than the migration failing halfway.
    op.execute("DELETE FROM form_questions WHERE kind = 'number'")
    op.drop_constraint("ck_form_questions_kind", "form_questions", type_="check")
    op.create_check_constraint("ck_form_questions_kind", "form_questions", _KINDS_BEFORE)
    op.drop_column("form_questions", "unit")
    op.drop_column("form_questions", "max_value")
    op.drop_column("form_questions", "min_value")
