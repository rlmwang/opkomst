"""merge forms + event image branches

Revision ID: 85f09654b16b
Revises: 37e4b9e81432, 3e56b3f6d717
Create Date: 2026-06-06 21:32:01.740432
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '85f09654b16b'
# Merge migrations declare both parent revisions as a tuple — same
# convention every other Alembic merge file uses. Suppress the
# ``str | None`` mismatch (Alembic's own type hint is wrong for
# the merge case; runtime accepts the tuple just fine).
down_revision: str | None = ('37e4b9e81432', '3e56b3f6d717')  # type: ignore[assignment]
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
