"""scd2 events

Revision ID: 56a40a5cd072
Revises: 190f36ee419b
Create Date: 2026-04-27 10:10:54.504833
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "56a40a5cd072"
down_revision: str | None = "190f36ee419b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add SCD2 columns as nullable so existing rows survive the add.
    op.add_column("events", sa.Column("entity_id", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("valid_from", sa.DateTime(), nullable=True))
    op.add_column("events", sa.Column("valid_until", sa.DateTime(), nullable=True))
    op.add_column("events", sa.Column("changed_by", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("change_kind", sa.Text(), nullable=True))

    # 2. Backfill: every existing event becomes its own first version.
    op.execute(
        "UPDATE events SET "
        "entity_id = id, "
        "valid_from = created_at, "
        "valid_until = NULL, "
        "changed_by = created_by, "
        "change_kind = 'created'"
    )

    # 3. Tighten constraints + add indexes + FK on changed_by.
    op.alter_column("events", "entity_id", existing_type=sa.Text(), nullable=False)
    op.alter_column("events", "valid_from", existing_type=sa.DateTime(), nullable=False)
    op.alter_column("events", "changed_by", existing_type=sa.Text(), nullable=False)
    op.alter_column("events", "change_kind", existing_type=sa.Text(), nullable=False)
    op.create_index("ix_events_entity_id", "events", ["entity_id"])
    op.create_index("ix_events_valid_until", "events", ["valid_until"])
    # Slug must be unique among current versions only — multiple
    # history rows can share a slug. Replace the column-level unique
    # index with a partial unique.
    op.drop_index("ix_events_slug", table_name="events")
    op.create_index("ix_events_slug", "events", ["slug"], unique=False)
    op.create_index(
        "uq_events_slug_current",
        "events",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )
    op.create_foreign_key(
        "fk_events_changed_by_users", "events", "users", ["changed_by"], ["id"]
    )

    # 4. Drop the FKs from child tables — event_id now points at
    #    Event.entity_id, which is not unique across all rows so a real
    #    FK is impossible. Integrity is enforced in code.
    op.drop_constraint("signups_event_id_fkey", "signups", type_="foreignkey")
    op.drop_constraint(
        "feedback_tokens_event_id_fkey", "feedback_tokens", type_="foreignkey"
    )
    op.drop_constraint(
        "feedback_responses_event_id_fkey", "feedback_responses", type_="foreignkey"
    )


def downgrade() -> None:
    op.create_foreign_key(
        "fk_signups_event_id_events", "signups", "events", ["event_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_feedback_tokens_event_id_events",
        "feedback_tokens",
        "events",
        ["event_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_feedback_responses_event_id_events",
        "feedback_responses",
        "events",
        ["event_id"],
        ["id"],
    )

    op.drop_constraint("fk_events_changed_by_users", "events", type_="foreignkey")
    op.drop_index("uq_events_slug_current", table_name="events")
    op.drop_index("ix_events_slug", table_name="events")
    op.create_index("ix_events_slug", "events", ["slug"], unique=True)
    op.drop_index("ix_events_valid_until", table_name="events")
    op.drop_index("ix_events_entity_id", table_name="events")
    op.drop_column("events", "change_kind")
    op.drop_column("events", "changed_by")
    op.drop_column("events", "valid_until")
    op.drop_column("events", "valid_from")
    op.drop_column("events", "entity_id")
