"""events: optional location, switches default off

Revision ID: fb1c34bb826c
Revises: e58c2a41f9d3
Create Date: 2026-08-26 09:00:08.273903
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fb1c34bb826c"
down_revision: str | None = "e58c2a41f9d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The switches that carry a server-side default. ``feedback_enabled`` and
# ``reminder_enabled`` never had one: every write names them.
SWITCHES = ("source_enabled", "help_enabled", "listed")


def upgrade() -> None:
    op.alter_column("events", "location", existing_type=sa.TEXT(), nullable=True)
    for column in SWITCHES:
        op.alter_column("events", column, existing_type=sa.Boolean(), server_default=sa.text("false"))


def downgrade() -> None:
    for column in SWITCHES:
        op.alter_column("events", column, existing_type=sa.Boolean(), server_default=sa.text("true"))
    op.alter_column("events", "location", existing_type=sa.TEXT(), nullable=False)
