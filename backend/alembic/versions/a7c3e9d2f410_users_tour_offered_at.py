"""users: when the tour was offered

One nullable timestamp on the user's row: when the landing page's one
offer of a guided tour was answered, either way. The tour records
nothing else (``docs/design-tour.md`` chapter 9).

Revision ID: a7c3e9d2f410
Revises: e2a7c40f91bd
"""

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9d2f410"
down_revision: str | None = "e2a7c40f91bd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tour_offered_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tour_offered_at")
