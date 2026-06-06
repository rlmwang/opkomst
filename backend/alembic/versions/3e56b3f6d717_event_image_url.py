"""event image_url + image_artist_instagram

Revision ID: 3e56b3f6d717
Revises: d6f9cc45552a
Create Date: 2026-06-06 14:21:15.653465
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '3e56b3f6d717'
down_revision: str | None = 'd6f9cc45552a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("image_url", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("image_artist_instagram", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "image_artist_instagram")
    op.drop_column("events", "image_url")
