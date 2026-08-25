"""tenants have a kind: organisation or personal

An organisation is named in ``TENANTS`` and has a committed brand; a
personal tenant is one person who typed an address at the root. Every
existing tenant is an organisation — personal ones can only come from
the root page, which doesn't exist yet at this revision.

Revision ID: c93a17e5b208
Revises: b7f21c8a3d54
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c93a17e5b208"
down_revision: str | None = "b7f21c8a3d54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("kind", sa.Text(), nullable=True))
    op.execute("UPDATE tenants SET kind = 'organisation'")
    op.alter_column("tenants", "kind", existing_type=sa.Text(), nullable=False)
    op.create_check_constraint("ck_tenants_kind", "tenants", "kind IN ('organisation', 'personal')")
    # Personal tenants are found by the address of their one user, and
    # the sync sweep has to tell them from the organisations it manages.
    op.create_index("ix_tenants_kind", "tenants", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_tenants_kind", table_name="tenants")
    op.drop_constraint("ck_tenants_kind", "tenants", type_="check")
    op.drop_column("tenants", "kind")
