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


def _is_sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


def upgrade() -> None:
    # 1. Add SCD2 columns as nullable so existing rows survive the add.
    with op.batch_alter_table("events") as b:
        b.add_column(sa.Column("entity_id", sa.Text(), nullable=True))
        b.add_column(sa.Column("valid_from", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("valid_until", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("changed_by", sa.Text(), nullable=True))
        b.add_column(sa.Column("change_kind", sa.Text(), nullable=True))

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
    with op.batch_alter_table("events") as b:
        b.alter_column("entity_id", existing_type=sa.Text(), nullable=False)
        b.alter_column("valid_from", existing_type=sa.DateTime(), nullable=False)
        b.alter_column("changed_by", existing_type=sa.Text(), nullable=False)
        b.alter_column("change_kind", existing_type=sa.Text(), nullable=False)
        b.create_index("ix_events_entity_id", ["entity_id"])
        b.create_index("ix_events_valid_until", ["valid_until"])
        # Slug must be unique among current versions only — multiple
        # history rows can share a slug. Replace the column-level unique
        # index with a partial unique.
        b.drop_index("ix_events_slug")
        b.create_index("ix_events_slug", ["slug"], unique=False)
        b.create_index(
            "uq_events_slug_current",
            ["slug"],
            unique=True,
            sqlite_where=sa.text("valid_until IS NULL"),
            postgresql_where=sa.text("valid_until IS NULL"),
        )
        b.create_foreign_key("fk_events_changed_by_users", "users", ["changed_by"], ["id"])

    # 4. Drop the FKs from child tables — event_id now points at
    #    Event.entity_id, which is not unique across all rows so a real
    #    FK is impossible. Integrity is enforced in code.
    if _is_sqlite():
        # SQLite FKs are unnamed; passing a naming_convention to batch
        # makes alembic synthesise a name when reflecting the table.
        nc = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
        with op.batch_alter_table("signups", naming_convention=nc) as b:
            b.drop_constraint("fk_signups_event_id_events", type_="foreignkey")
        with op.batch_alter_table("feedback_tokens", naming_convention=nc) as b:
            b.drop_constraint("fk_feedback_tokens_event_id_events", type_="foreignkey")
        with op.batch_alter_table("feedback_responses", naming_convention=nc) as b:
            b.drop_constraint("fk_feedback_responses_event_id_events", type_="foreignkey")
    else:
        # Postgres default convention is ``<table>_<column>_fkey``.
        op.drop_constraint("signups_event_id_fkey", "signups", type_="foreignkey")
        op.drop_constraint("feedback_tokens_event_id_fkey", "feedback_tokens", type_="foreignkey")
        op.drop_constraint("feedback_responses_event_id_fkey", "feedback_responses", type_="foreignkey")


def downgrade() -> None:
    # Re-add the FKs (point at events.id again — original shape).
    if _is_sqlite():
        with op.batch_alter_table("signups") as b:
            b.create_foreign_key("fk_signups_event_id_events", "events", ["event_id"], ["id"])
        with op.batch_alter_table("feedback_tokens") as b:
            b.create_foreign_key("fk_feedback_tokens_event_id_events", "events", ["event_id"], ["id"])
        with op.batch_alter_table("feedback_responses") as b:
            b.create_foreign_key("fk_feedback_responses_event_id_events", "events", ["event_id"], ["id"])
    else:
        op.create_foreign_key("fk_signups_event_id_events", "signups", "events", ["event_id"], ["id"])
        op.create_foreign_key("fk_feedback_tokens_event_id_events", "feedback_tokens", "events", ["event_id"], ["id"])
        op.create_foreign_key(
            "fk_feedback_responses_event_id_events", "feedback_responses", "events", ["event_id"], ["id"]
        )

    with op.batch_alter_table("events") as b:
        b.drop_constraint("fk_events_changed_by_users", type_="foreignkey")
        b.drop_index("uq_events_slug_current")
        b.drop_index("ix_events_slug")
        b.create_index("ix_events_slug", ["slug"], unique=True)
        b.drop_index("ix_events_valid_until")
        b.drop_index("ix_events_entity_id")
        b.drop_column("change_kind")
        b.drop_column("changed_by")
        b.drop_column("valid_until")
        b.drop_column("valid_from")
        b.drop_column("entity_id")
