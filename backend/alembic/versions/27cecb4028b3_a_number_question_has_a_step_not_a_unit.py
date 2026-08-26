"""a number question has a step not a unit

The unit was a word rendered beside the answer; it named the number
without controlling it, and a number question needs the opposite. The
step says which numbers count as an answer: 5 accepts 0, 5, 10, counted
from the lowest allowed number when there is one.

Revision ID: 27cecb4028b3
Revises: 2f795bf98301
Create Date: 2026-08-26 20:09:32.653424
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '27cecb4028b3'
down_revision: str | None = '2f795bf98301'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('form_questions', sa.Column('step', sa.Integer(), nullable=True))
    op.drop_column('form_questions', 'unit')


def downgrade() -> None:
    op.add_column('form_questions', sa.Column('unit', sa.TEXT(), autoincrement=False, nullable=True))
    op.drop_column('form_questions', 'step')
