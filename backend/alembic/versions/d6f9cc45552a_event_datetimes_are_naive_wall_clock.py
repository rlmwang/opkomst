"""event datetimes are naive wall-clock

Revision ID: d6f9cc45552a
Revises: defb7b12f7c1
Create Date: 2026-06-06 10:13:57.449455
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd6f9cc45552a'
down_revision: str | None = 'defb7b12f7c1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Convert TIMESTAMPTZ → TIMESTAMP. The default cast strips the
    # offset relative to the session timezone, which is UTC in CI and
    # production — that would land the wall-clock values 2h off in
    # CEST. ``AT TIME ZONE 'Europe/Amsterdam'`` makes the conversion
    # session-TZ-independent: each row becomes its Amsterdam wall
    # clock, which is exactly the semantic we now want.
    op.alter_column(
        "events", "starts_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="starts_at AT TIME ZONE 'Europe/Amsterdam'",
    )
    op.alter_column(
        "events", "ends_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="ends_at AT TIME ZONE 'Europe/Amsterdam'",
    )


def downgrade() -> None:
    # Symmetric reverse: read the naive wall-clock as Europe/Amsterdam
    # and tag it with that zone, producing a UTC-equivalent
    # TIMESTAMPTZ.
    op.alter_column(
        "events", "ends_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        postgresql_using="ends_at AT TIME ZONE 'Europe/Amsterdam'",
    )
    op.alter_column(
        "events", "starts_at",
        existing_type=sa.DateTime(),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=False,
        postgresql_using="starts_at AT TIME ZONE 'Europe/Amsterdam'",
    )
