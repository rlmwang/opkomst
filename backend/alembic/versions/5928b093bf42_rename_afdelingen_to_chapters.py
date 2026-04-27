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


def _is_sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


def upgrade() -> None:
    # Rename table afdelingen -> chapters
    op.rename_table("afdelingen", "chapters")

    # Rename ix_afdelingen_* indexes -> ix_chapters_*
    if _is_sqlite():
        op.execute("DROP INDEX IF EXISTS ix_afdelingen_entity_id")
        op.execute("DROP INDEX IF EXISTS ix_afdelingen_valid_until")
        op.create_index("ix_chapters_entity_id", "chapters", ["entity_id"])
        op.create_index("ix_chapters_valid_until", "chapters", ["valid_until"])
    else:
        op.execute("ALTER INDEX ix_afdelingen_entity_id RENAME TO ix_chapters_entity_id")
        op.execute("ALTER INDEX ix_afdelingen_valid_until RENAME TO ix_chapters_valid_until")

    # Rename users.afdeling_id -> users.chapter_id
    with op.batch_alter_table("users") as batch:
        batch.alter_column("afdeling_id", new_column_name="chapter_id")
    op.execute("DROP INDEX IF EXISTS ix_users_afdeling_id")
    op.create_index("ix_users_chapter_id", "users", ["chapter_id"])

    # Rename events.afdeling_id -> events.chapter_id
    with op.batch_alter_table("events") as batch:
        batch.alter_column("afdeling_id", new_column_name="chapter_id")
    op.execute("DROP INDEX IF EXISTS ix_events_afdeling_id")
    op.create_index("ix_events_chapter_id", "events", ["chapter_id"])


def downgrade() -> None:
    with op.batch_alter_table("events") as batch:
        batch.alter_column("chapter_id", new_column_name="afdeling_id")
    op.execute("DROP INDEX IF EXISTS ix_events_chapter_id")
    op.create_index("ix_events_afdeling_id", "events", ["afdeling_id"])

    with op.batch_alter_table("users") as batch:
        batch.alter_column("chapter_id", new_column_name="afdeling_id")
    op.execute("DROP INDEX IF EXISTS ix_users_chapter_id")
    op.create_index("ix_users_afdeling_id", "users", ["afdeling_id"])

    if _is_sqlite():
        op.execute("DROP INDEX IF EXISTS ix_chapters_entity_id")
        op.execute("DROP INDEX IF EXISTS ix_chapters_valid_until")
    else:
        op.execute("ALTER INDEX ix_chapters_entity_id RENAME TO ix_afdelingen_entity_id")
        op.execute("ALTER INDEX ix_chapters_valid_until RENAME TO ix_afdelingen_valid_until")

    op.rename_table("chapters", "afdelingen")
    if _is_sqlite():
        op.create_index("ix_afdelingen_entity_id", "afdelingen", ["entity_id"])
        op.create_index("ix_afdelingen_valid_until", "afdelingen", ["valid_until"])
