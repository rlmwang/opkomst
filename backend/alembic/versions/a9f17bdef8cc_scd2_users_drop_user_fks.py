"""scd2 users + drop user fks

Revision ID: a9f17bdef8cc
Revises: 56a40a5cd072
Create Date: 2026-04-27 10:22:11.641133

Promotes the ``users`` table to strict SCD2 and drops every FK that
targets ``users.id``. After this migration:

* ``user.entity_id`` is the stable logical id; JWTs sign it; DTOs
  expose it as ``id``.
* References from ``events.created_by``, ``events.changed_by``,
  ``afdelingen.changed_by``, ``audit_log.actor_id``,
  ``audit_log.target_id`` all point at ``user.entity_id`` (no FK
  constraint because entity_id isn't unique across rows; integrity
  is enforced by routing reads through ``services.scd2.current``).

Existing user rows survive: each becomes its own first version
(``entity_id = id``, ``valid_from = created_at``, ``changed_by = id``,
``change_kind = 'created'``). All foreign references already point at
that ``id``, which equals the new ``entity_id`` post-backfill — the
data move is a no-op, only the constraint shape changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9f17bdef8cc"
down_revision: str | None = "56a40a5cd072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add SCD2 columns to users as nullable so existing rows survive.
    op.add_column("users", sa.Column("entity_id", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("valid_from", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("valid_until", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("changed_by", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("change_kind", sa.Text(), nullable=True))

    # 2. Backfill: every existing user becomes its own first version.
    op.execute(
        "UPDATE users SET "
        "entity_id = id, "
        "valid_from = created_at, "
        "valid_until = NULL, "
        "changed_by = id, "
        "change_kind = 'created'"
    )

    # 3. Tighten constraints + add indexes + replace email unique with
    #    a partial unique over current versions only.
    op.alter_column("users", "entity_id", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "valid_from", existing_type=sa.DateTime(), nullable=False)
    op.alter_column("users", "changed_by", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "change_kind", existing_type=sa.Text(), nullable=False)
    op.create_index("ix_users_entity_id", "users", ["entity_id"])
    op.create_index("ix_users_valid_until", "users", ["valid_until"])
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index(
        "uq_users_email_current",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("valid_until IS NULL"),
    )

    # 4. Drop FKs on every column that points at users.id. After this
    #    they all point at user.entity_id (data unchanged, since
    #    entity_id == id post-backfill).
    op.drop_constraint("afdelingen_changed_by_fkey", "afdelingen", type_="foreignkey")
    op.drop_constraint("audit_log_actor_id_fkey", "audit_log", type_="foreignkey")
    op.drop_constraint("audit_log_target_id_fkey", "audit_log", type_="foreignkey")
    op.drop_constraint("events_created_by_fkey", "events", type_="foreignkey")
    op.drop_constraint("fk_events_changed_by_users", "events", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "afdelingen_changed_by_fkey", "afdelingen", "users", ["changed_by"], ["id"]
    )
    op.create_foreign_key(
        "audit_log_actor_id_fkey", "audit_log", "users", ["actor_id"], ["id"]
    )
    op.create_foreign_key(
        "audit_log_target_id_fkey", "audit_log", "users", ["target_id"], ["id"]
    )
    op.create_foreign_key(
        "events_created_by_fkey", "events", "users", ["created_by"], ["id"]
    )
    op.create_foreign_key(
        "fk_events_changed_by_users", "events", "users", ["changed_by"], ["id"]
    )

    op.drop_index("uq_users_email_current", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.drop_index("ix_users_valid_until", table_name="users")
    op.drop_index("ix_users_entity_id", table_name="users")
    op.drop_column("users", "change_kind")
    op.drop_column("users", "changed_by")
    op.drop_column("users", "valid_until")
    op.drop_column("users", "valid_from")
    op.drop_column("users", "entity_id")
