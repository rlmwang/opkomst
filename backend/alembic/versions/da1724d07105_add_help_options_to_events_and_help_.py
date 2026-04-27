"""add help_options to events and help_choices to signups

Revision ID: da1724d07105
Revises: 5928b093bf42
Create Date: 2026-04-27 14:32:23.788786
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "da1724d07105"
down_revision: str | None = "5928b093bf42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL columns need a server_default so existing rows on a
    # populated DB get a sane value. Empty list is the right default —
    # opt-in feature on events, attendees skipping the question on
    # signups.
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("help_options", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("help_choices", sa.JSON(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.drop_column("help_choices")

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_column("help_options")
