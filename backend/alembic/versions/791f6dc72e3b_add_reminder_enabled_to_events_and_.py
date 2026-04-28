"""add reminder_enabled to events and reminder_email tracking to signups

Revision ID: 791f6dc72e3b
Revises: be90a6723163
Create Date: 2026-04-27 19:53:50.516504
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "791f6dc72e3b"
down_revision: str | None = "be90a6723163"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New event toggle. Defaults to FALSE for existing rows;
    # organisers opt in per event.
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "reminder_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    # Parallel set of reminder-tracking fields on signups,
    # mirroring the existing feedback_email_* columns.
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "reminder_email_status",
                sa.Text(),
                nullable=False,
                server_default="not_applicable",
            )
        )
        batch_op.add_column(
            sa.Column("reminder_sent_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("reminder_message_id", sa.Text(), nullable=True)
        )
        batch_op.create_index(
            "ix_signups_reminder_email_status",
            ["reminder_email_status"],
        )
        batch_op.create_index(
            "ix_signups_reminder_message_id",
            ["reminder_message_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.drop_index("ix_signups_reminder_message_id")
        batch_op.drop_index("ix_signups_reminder_email_status")
        batch_op.drop_column("reminder_message_id")
        batch_op.drop_column("reminder_sent_at")
        batch_op.drop_column("reminder_email_status")
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_column("reminder_enabled")
