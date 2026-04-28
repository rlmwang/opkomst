"""make q3_welcome required

Flips ``feedback_questions.required = True`` for ``q3_welcome``
so the public form treats it like q1/q2 (asks for a rating
before accepting submission).

Revision ID: 4a8e1f3c0a91
Revises: 2b9a94e0632f
Create Date: 2026-04-28 02:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a8e1f3c0a91"
down_revision: str | None = "2b9a94e0632f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_questions = sa.table(
    "feedback_questions",
    sa.column("key", sa.Text),
    sa.column("required", sa.Boolean),
)


def upgrade() -> None:
    op.execute(
        _questions.update()
        .where(_questions.c.key == "q3_welcome")
        .values(required=True)
    )


def downgrade() -> None:
    op.execute(
        _questions.update()
        .where(_questions.c.key == "q3_welcome")
        .values(required=False)
    )
