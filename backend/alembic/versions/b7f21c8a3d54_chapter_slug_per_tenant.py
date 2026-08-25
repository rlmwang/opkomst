"""chapter slugs are unique per organisation

The agenda moved from ``/e/{chapter}`` to ``/{tenant}/{chapter}``, so
the tenant now separates two organisations that each have an Amsterdam.
The live-scoped unique index gains ``tenant_id``.

No data changes: today's slugs were unique globally, which is stricter
than the new rule.

Revision ID: b7f21c8a3d54
Revises: a1c4e97b2d10
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7f21c8a3d54"
down_revision: str | None = "a1c4e97b2d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_chapters_slug_live", table_name="chapters")
    op.create_index(
        "uq_chapters_slug_live",
        "chapters",
        ["tenant_id", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_chapters_slug_live", table_name="chapters")
    op.create_index(
        "uq_chapters_slug_live",
        "chapters",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
