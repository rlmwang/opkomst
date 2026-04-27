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


def _is_sqlite() -> bool:
    return op.get_context().dialect.name == "sqlite"


# Naming convention used for SQLite batch-mode constraint discovery.
_NC = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def upgrade() -> None:
    # 1. Add SCD2 columns to users as nullable so existing rows survive.
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("entity_id", sa.Text(), nullable=True))
        b.add_column(sa.Column("valid_from", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("valid_until", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("changed_by", sa.Text(), nullable=True))
        b.add_column(sa.Column("change_kind", sa.Text(), nullable=True))

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
    with op.batch_alter_table("users") as b:
        b.alter_column("entity_id", existing_type=sa.Text(), nullable=False)
        b.alter_column("valid_from", existing_type=sa.DateTime(), nullable=False)
        b.alter_column("changed_by", existing_type=sa.Text(), nullable=False)
        b.alter_column("change_kind", existing_type=sa.Text(), nullable=False)
        b.create_index("ix_users_entity_id", ["entity_id"])
        b.create_index("ix_users_valid_until", ["valid_until"])
        b.drop_index("ix_users_email")
        b.create_index("ix_users_email", ["email"], unique=False)
        b.create_index(
            "uq_users_email_current",
            ["email"],
            unique=True,
            sqlite_where=sa.text("valid_until IS NULL"),
            postgresql_where=sa.text("valid_until IS NULL"),
        )

    # 4. Drop FKs on every column that points at users.id. After this
    #    they all point at user.entity_id (data unchanged, since
    #    entity_id == id post-backfill).
    if _is_sqlite():
        with op.batch_alter_table("afdelingen", naming_convention=_NC) as b:
            b.drop_constraint("fk_afdelingen_changed_by_users", type_="foreignkey")
        with op.batch_alter_table("audit_log", naming_convention=_NC) as b:
            b.drop_constraint("fk_audit_log_actor_id_users", type_="foreignkey")
            b.drop_constraint("fk_audit_log_target_id_users", type_="foreignkey")
        with op.batch_alter_table("events", naming_convention=_NC) as b:
            b.drop_constraint("fk_events_created_by_users", type_="foreignkey")
            b.drop_constraint("fk_events_changed_by_users", type_="foreignkey")
    else:
        op.drop_constraint("afdelingen_changed_by_fkey", "afdelingen", type_="foreignkey")
        op.drop_constraint("audit_log_actor_id_fkey", "audit_log", type_="foreignkey")
        op.drop_constraint("audit_log_target_id_fkey", "audit_log", type_="foreignkey")
        op.drop_constraint("events_created_by_fkey", "events", type_="foreignkey")
        op.drop_constraint("fk_events_changed_by_users", "events", type_="foreignkey")


def downgrade() -> None:
    if _is_sqlite():
        with op.batch_alter_table("afdelingen") as b:
            b.create_foreign_key("fk_afdelingen_changed_by_users", "users", ["changed_by"], ["id"])
        with op.batch_alter_table("audit_log") as b:
            b.create_foreign_key("fk_audit_log_actor_id_users", "users", ["actor_id"], ["id"])
            b.create_foreign_key("fk_audit_log_target_id_users", "users", ["target_id"], ["id"])
        with op.batch_alter_table("events") as b:
            b.create_foreign_key("fk_events_created_by_users", "users", ["created_by"], ["id"])
            b.create_foreign_key("fk_events_changed_by_users", "users", ["changed_by"], ["id"])
    else:
        op.create_foreign_key("afdelingen_changed_by_fkey", "afdelingen", "users", ["changed_by"], ["id"])
        op.create_foreign_key("audit_log_actor_id_fkey", "audit_log", "users", ["actor_id"], ["id"])
        op.create_foreign_key("audit_log_target_id_fkey", "audit_log", "users", ["target_id"], ["id"])
        op.create_foreign_key("events_created_by_fkey", "events", "users", ["created_by"], ["id"])
        op.create_foreign_key("fk_events_changed_by_users", "events", "users", ["changed_by"], ["id"])

    with op.batch_alter_table("users") as b:
        b.drop_index("uq_users_email_current")
        b.drop_index("ix_users_email")
        b.create_index("ix_users_email", ["email"], unique=True)
        b.drop_index("ix_users_valid_until")
        b.drop_index("ix_users_entity_id")
        b.drop_column("change_kind")
        b.drop_column("changed_by")
        b.drop_column("valid_until")
        b.drop_column("valid_from")
        b.drop_column("entity_id")
