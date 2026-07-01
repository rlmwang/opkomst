"""widen shift-event kinds with covered + inherited

Revision ID: 6be2c0a71d3e
Revises: 58ca1def210f
Create Date: 2026-07-01 13:55:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "6be2c0a71d3e"
down_revision: str | None = "58ca1def210f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "kind IN ('assigned', 'claimed', 'completed', 'deferred', 'missed')"
_NEW = "kind IN ('assigned', 'claimed', 'covered', 'inherited', 'completed', 'deferred', 'missed')"


def upgrade() -> None:
    op.drop_constraint("ck_shift_events_kind", "shift_events", type_="check")
    op.create_check_constraint("ck_shift_events_kind", "shift_events", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_shift_events_kind", "shift_events", type_="check")
    op.create_check_constraint("ck_shift_events_kind", "shift_events", _OLD)
