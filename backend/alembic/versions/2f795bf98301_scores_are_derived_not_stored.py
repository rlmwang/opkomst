"""scores are derived not stored

The three columns that froze a score at submit time. What is kept is
the answer; the score is that answer marked against the quiz as it
stands now, so an organiser who fixes a key or re-weights a question
sees every score follow (``services/quizzes``).

Reversing this restores the columns empty, which is honest: the numbers
they held were snapshots, and a snapshot cannot be recovered from a
schema.

Revision ID: 2f795bf98301
Revises: f15dc6f85875
Create Date: 2026-08-26 19:31:28.610340
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '2f795bf98301'
down_revision: str | None = 'f15dc6f85875'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column('form_responses', 'awarded')
    op.drop_column('form_submissions', 'max_score')
    op.drop_column('form_submissions', 'score')


def downgrade() -> None:
    op.add_column('form_submissions', sa.Column('score', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('form_submissions', sa.Column('max_score', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('form_responses', sa.Column('awarded', sa.INTEGER(), autoincrement=False, nullable=True))
