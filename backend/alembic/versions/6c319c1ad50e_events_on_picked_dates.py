"""events: recur on picked dates instead of a pattern

An organiser can list the dates themselves, the way a date poll picks
them, instead of describing a weekly pattern.

Revision ID: 6c319c1ad50e
Revises: 03691adc14eb
"""

import sqlalchemy as sa
from alembic import op

revision: str = "6c319c1ad50e"
down_revision: str | None = "03691adc14eb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("picked_dates", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    # The twin carries no defaults; the one here only fills the rows
    # already archived.
    op.add_column(
        "events_archive", sa.Column("picked_dates", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
    )
    op.alter_column("events_archive", "picked_dates", server_default=None)


def downgrade() -> None:
    op.drop_column("events_archive", "picked_dates")
    op.drop_column("events", "picked_dates")
