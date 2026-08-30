"""email dispatches are a queue, sends are a count

A dispatch row used to be a record of a send: created pending, flipped
to sent or failed, kept for ever with its address nulled. It is work
now. The row is deleted when the send finishes, which makes the address'
lifetime exactly the work's lifetime, and keeps the table the size of
the queue rather than the size of everything ever sent.

What is left behind is ``email_send_counts``: how many sends of one
channel succeeded and failed for one occurrence on one day. That is
what the organiser page counts and what the daily send cap measures.

The rows already finalised in production are folded into that tally
before they are deleted, so the counts do not start at zero.

Revision ID: f3483b5b6fa2
Revises: 22d316267bfb
Create Date: 2026-08-29 08:45:03.818710
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3483b5b6fa2"
down_revision: str | None = "22d316267bfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_send_counts",
        sa.Column("occurrence_id", sa.Text(), nullable=False),
        # The type already exists (``email_dispatches`` uses it), so this
        # references it rather than creating it a second time.
        sa.Column(
            "channel",
            postgresql.ENUM("REMINDER", "FEEDBACK", name="email_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("sent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["occurrence_id"], ["occurrences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "occurrence_id", "channel", "day", name="uq_email_send_counts_occurrence_channel_day"
        ),
    )
    op.create_index(op.f("ix_email_send_counts_day"), "email_send_counts", ["day"], unique=False)
    op.create_index(
        op.f("ix_email_send_counts_occurrence_id"), "email_send_counts", ["occurrence_id"], unique=False
    )
    op.create_index(op.f("ix_email_send_counts_tenant_id"), "email_send_counts", ["tenant_id"], unique=False)

    # Fold the sends that already happened into the tally. The day is
    # when the send finished, falling back to when the row was made for
    # anything finalised before ``sent_at`` was being written. ``id`` is
    # a uuid7 in the application; here any unique text will do, and
    # ``gen_random_uuid()`` is available without an extension on PG 13+.
    op.execute(
        """
        INSERT INTO email_send_counts
            (id, occurrence_id, channel, day, sent, failed, tenant_id, created_at, updated_at)
        SELECT
            gen_random_uuid()::text,
            d.occurrence_id,
            d.channel,
            COALESCE(d.sent_at, d.created_at)::date,
            COUNT(*) FILTER (WHERE d.status = 'SENT'),
            COUNT(*) FILTER (WHERE d.status = 'FAILED'),
            d.tenant_id,
            NOW(),
            NOW()
        FROM email_dispatches d
        WHERE d.status <> 'PENDING'
        GROUP BY d.occurrence_id, d.channel, COALESCE(d.sent_at, d.created_at)::date, d.tenant_id
        """
    )
    # Their rows have said everything they have to say.
    op.execute("DELETE FROM email_dispatches WHERE status <> 'PENDING'")

    op.drop_index(op.f("ix_dispatches_occurrence_channel_status"), table_name="email_dispatches")
    op.create_index(
        "ix_dispatches_occurrence_channel", "email_dispatches", ["occurrence_id", "channel"], unique=False
    )
    op.drop_column("email_dispatches", "status")
    op.drop_column("email_dispatches", "sent_at")
    # Nothing refers to the type once the column is gone.
    op.execute("DROP TYPE IF EXISTS email_status")


def downgrade() -> None:
    email_status = postgresql.ENUM("PENDING", "SENT", "FAILED", name="email_status")
    email_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "email_dispatches",
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    )
    op.add_column(
        "email_dispatches",
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "SENT", "FAILED", name="email_status", create_type=False),
            autoincrement=False,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.alter_column("email_dispatches", "status", server_default=None)
    op.drop_index("ix_dispatches_occurrence_channel", table_name="email_dispatches")
    op.create_index(
        op.f("ix_dispatches_occurrence_channel_status"),
        "email_dispatches",
        ["occurrence_id", "channel", "status"],
        unique=False,
    )
    op.drop_index(op.f("ix_email_send_counts_tenant_id"), table_name="email_send_counts")
    op.drop_index(op.f("ix_email_send_counts_occurrence_id"), table_name="email_send_counts")
    op.drop_index(op.f("ix_email_send_counts_day"), table_name="email_send_counts")
    op.drop_table("email_send_counts")
