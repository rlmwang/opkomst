"""make signup display_name and source_choice nullable

Revision ID: be90a6723163
Revises: da1724d07105
Create Date: 2026-04-27 19:13:04.795025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "be90a6723163"
down_revision: str | None = "da1724d07105"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Both fields are now optional on the public sign-up form. Drop
    # NOT NULL so visitors who skip them store real NULLs instead of
    # sentinel empty strings.
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.alter_column("display_name", existing_type=sa.Text(), nullable=True)
        batch_op.alter_column("source_choice", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.alter_column("source_choice", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("display_name", existing_type=sa.Text(), nullable=False)
