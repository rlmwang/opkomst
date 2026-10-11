"""events: end after weeks, after a number of sessions, or on a date

A recurring event used to end only after a number of weeks, which left
"five times every two weeks" to arithmetic. It now ends by at most one
of three bounds; none of them is open-ended.

Revision ID: 03691adc14eb
Revises: 0425e980177f
"""

import sqlalchemy as sa
from alembic import op

revision: str = "03691adc14eb"
down_revision: str | None = "0425e980177f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("events", "events_archive"):
        op.add_column(table, sa.Column("span_sessions", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("span_until", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_events_one_end", "events", "num_nonnulls(span_weeks, span_sessions, span_until) <= 1"
    )


def downgrade() -> None:
    op.drop_constraint("ck_events_one_end", "events", type_="check")
    for table in ("events", "events_archive"):
        op.drop_column(table, "span_until")
        op.drop_column(table, "span_sessions")
