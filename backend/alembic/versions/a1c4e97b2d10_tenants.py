"""tenants: one owner per row

Creates the ``tenants`` table, inserts the ``rsp`` tenant that every
existing row belongs to, and puts a ``tenant_id`` on all 27 other
tables — NOT NULL, indexed, RESTRICT back to ``tenants``.

Child rows carry their parent's tenant denormalized. That is the point:
every read filter and every uniqueness rule becomes a single predicate
on the row itself. ``tests/test_tenancy.py`` guards both halves — the
column exists everywhere, and a child never disagrees with its parent.

The backfill is real work: this install is deployed, so every existing
row is assigned to ``rsp`` before the column goes NOT NULL.

Revision ID: a1c4e97b2d10
Revises: 6023884ff187
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e97b2d10"
down_revision: str | None = "6023884ff187"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Every table that gains the column. The tenant of a row is its own
# root's tenant; with a single tenant at migration time the backfill is
# the same statement for all of them.
TABLES = (
    "chapters",
    "chores",
    "datepoll_responses",
    "datepoll_slots",
    "datepoll_submissions",
    "datepolls",
    "email_dispatches",
    "enrollments",
    "events",
    "feedback_responses",
    "feedback_tokens",
    "form_questions",
    "form_responses",
    "form_submissions",
    "forms",
    "login_tokens",
    "occurrences",
    "registration_tokens",
    "registrations",
    "rosters",
    "shift_events",
    "shifts",
    "signups",
    "user_chapters",
    "users",
    "volunteer_availability",
    "volunteers",
)

# The tenant every pre-existing row belongs to. A fixed id keeps the
# migration deterministic — re-running it on a copy of the database
# produces the same rows.
RSP_ID = "01988f00-0000-7000-8000-000000000001"


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenants_deleted_at", "tenants", ["deleted_at"])
    op.create_index(
        "uq_tenants_slug_live",
        "tenants",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_tenants_name_live",
        "tenants",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.execute(
        sa.text(
            "INSERT INTO tenants (id, slug, name, created_at, updated_at) "
            "VALUES (:id, 'rsp', 'RSP', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).bindparams(id=RSP_ID)
    )

    for table in TABLES:
        op.add_column(table, sa.Column("tenant_id", sa.Text(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET tenant_id = :id").bindparams(id=RSP_ID))
        op.alter_column(table, "tenant_id", existing_type=sa.Text(), nullable=False)
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_foreign_key(
            f"fk_{table}_tenant_id",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # Uniqueness that was global becomes per organisation: the same
    # email can organise for two of them, and each may have its own
    # "Amsterdam". The chapter *slug* stays globally unique — the public
    # agenda at ``/e/{slug}`` carries no tenant.
    op.drop_index("uq_users_email_live", table_name="users")
    op.create_index(
        "uq_users_email_live",
        "users",
        ["tenant_id", "email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("uq_chapters_name_live", table_name="chapters")
    op.create_index(
        "uq_chapters_name_live",
        "chapters",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_chapters_name_live", table_name="chapters")
    op.create_index(
        "uq_chapters_name_live",
        "chapters",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("uq_users_email_live", table_name="users")
    op.create_index(
        "uq_users_email_live",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for table in TABLES:
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
    op.drop_index("uq_tenants_name_live", table_name="tenants")
    op.drop_index("uq_tenants_slug_live", table_name="tenants")
    op.drop_index("ix_tenants_deleted_at", table_name="tenants")
    op.drop_table("tenants")
