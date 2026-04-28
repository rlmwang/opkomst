"""rename afdelingen to chapters

Revision ID: 5928b093bf42
Revises: db9748610549
Create Date: 2026-04-27 14:05:25.241345
"""

from collections.abc import Sequence

from alembic import op

revision: str = "5928b093bf42"
down_revision: str | None = "db9748610549"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("afdelingen", "chapters")
    op.execute("ALTER INDEX ix_afdelingen_entity_id RENAME TO ix_chapters_entity_id")
    op.execute("ALTER INDEX ix_afdelingen_valid_until RENAME TO ix_chapters_valid_until")

    op.alter_column("users", "afdeling_id", new_column_name="chapter_id")
    op.execute("ALTER INDEX ix_users_afdeling_id RENAME TO ix_users_chapter_id")

    op.alter_column("events", "afdeling_id", new_column_name="chapter_id")
    op.execute("ALTER INDEX ix_events_afdeling_id RENAME TO ix_events_chapter_id")


def downgrade() -> None:
    op.alter_column("events", "chapter_id", new_column_name="afdeling_id")
    op.execute("ALTER INDEX ix_events_chapter_id RENAME TO ix_events_afdeling_id")

    op.alter_column("users", "chapter_id", new_column_name="afdeling_id")
    op.execute("ALTER INDEX ix_users_chapter_id RENAME TO ix_users_afdeling_id")

    op.execute("ALTER INDEX ix_chapters_entity_id RENAME TO ix_afdelingen_entity_id")
    op.execute("ALTER INDEX ix_chapters_valid_until RENAME TO ix_afdelingen_valid_until")
    op.rename_table("chapters", "afdelingen")
