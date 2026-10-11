"""occurrences: one public link per event

The public sign-up page is the event's own slug, landing on the next
session, so a session no longer carries a slug of its own.

Revision ID: 0425e980177f
Revises: a7c3e9d2f410
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0425e980177f"
down_revision: str | None = "a7c3e9d2f410"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_occurrences_slug"), table_name="occurrences")
    op.drop_column("occurrences", "slug")
    op.drop_column("occurrences_archive", "slug")


def downgrade() -> None:
    for table in ("occurrences", "occurrences_archive"):
        op.add_column(table, sa.Column("slug", sa.Text(), nullable=True))
        op.execute(f"UPDATE {table} SET slug = substr(md5(id), 1, 8)")
        op.alter_column(table, "slug", nullable=False)
    op.create_index(op.f("ix_occurrences_slug"), "occurrences", ["slug"], unique=True)
