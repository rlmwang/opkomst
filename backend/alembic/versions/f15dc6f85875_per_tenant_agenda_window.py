"""per-tenant agenda window

Revision ID: f15dc6f85875
Revises: 9892ae52f22f
Create Date: 2026-08-26 18:24:59.641717
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f15dc6f85875"
down_revision: str | None = "9892ae52f22f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The two ends of the public agenda's rolling window, in days. The
    # server defaults are what every existing tenant starts with and
    # what a freshly inserted row gets; the bounds are the same ones
    # the schema enforces on the way in.
    op.add_column(
        "tenants",
        sa.Column("agenda_future_days", sa.Integer(), server_default=sa.text("31"), nullable=False),
    )
    op.add_column(
        "tenants",
        sa.Column("agenda_past_days", sa.Integer(), server_default=sa.text("60"), nullable=False),
    )
    op.create_check_constraint("ck_tenants_agenda_future_days", "tenants", "agenda_future_days BETWEEN 1 AND 365")
    op.create_check_constraint("ck_tenants_agenda_past_days", "tenants", "agenda_past_days BETWEEN 1 AND 365")


def downgrade() -> None:
    op.drop_constraint("ck_tenants_agenda_past_days", "tenants", type_="check")
    op.drop_constraint("ck_tenants_agenda_future_days", "tenants", type_="check")
    op.drop_column("tenants", "agenda_past_days")
    op.drop_column("tenants", "agenda_future_days")
