"""normalise email lifecycle into signup_email_dispatches

Replaces the parallel ``feedback_*`` / ``reminder_*`` column
triplets on ``signups`` with one normalised dispatch row per
(signup, channel) pair. Pre-launch — no preserve-old-and-add-new
shim. The migration creates the new table, backfills from the
old columns (skipping ``not_applicable`` rows since absence of
a dispatch row is the new representation of that state), then
drops the columns.

Revision ID: 2b9a94e0632f
Revises: 791f6dc72e3b
Create Date: 2026-04-28 01:14:31.793991
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from uuid_utils import uuid7

revision: str = "2b9a94e0632f"
down_revision: str | None = "791f6dc72e3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. New table.
    op.create_table(
        "signup_email_dispatches",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("signup_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "signup_id", "channel", name="uq_dispatches_signup_channel"
        ),
    )
    op.create_index(
        "ix_signup_email_dispatches_signup_id",
        "signup_email_dispatches",
        ["signup_id"],
    )
    op.create_index(
        "ix_dispatches_message_id",
        "signup_email_dispatches",
        ["message_id"],
    )
    op.create_index(
        "ix_dispatches_channel_status",
        "signup_email_dispatches",
        ["channel", "status"],
    )

    # 2. Backfill. Run as a Python loop so we can mint a uuid7 id
    # for each new dispatch row. Two channels × every signup with
    # a non-``not_applicable`` status on that channel.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, created_at, updated_at, "
            "feedback_email_status, feedback_sent_at, feedback_message_id, "
            "reminder_email_status, reminder_sent_at, reminder_message_id "
            "FROM signups"
        )
    ).fetchall()
    for row in rows:
        for channel, status_idx, sent_at_idx, msg_id_idx in (
            ("feedback", 3, 4, 5),
            ("reminder", 6, 7, 8),
        ):
            status = row[status_idx]
            if status == "not_applicable":
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO signup_email_dispatches "
                    "(id, created_at, updated_at, signup_id, channel, status, "
                    "message_id, sent_at) "
                    "VALUES (:id, :created_at, :updated_at, :signup_id, :channel, "
                    ":status, :message_id, :sent_at)"
                ),
                {
                    "id": str(uuid7()),
                    "created_at": row[1],
                    "updated_at": row[2],
                    "signup_id": row[0],
                    "channel": channel,
                    "status": status,
                    "message_id": row[msg_id_idx],
                    "sent_at": row[sent_at_idx],
                },
            )

    # 3. Drop the old columns.
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.drop_index("ix_signups_feedback_email_status")
        batch_op.drop_index("ix_signups_feedback_message_id")
        batch_op.drop_index("ix_signups_reminder_email_status")
        batch_op.drop_index("ix_signups_reminder_message_id")
        batch_op.drop_column("feedback_email_status")
        batch_op.drop_column("feedback_sent_at")
        batch_op.drop_column("feedback_message_id")
        batch_op.drop_column("reminder_email_status")
        batch_op.drop_column("reminder_sent_at")
        batch_op.drop_column("reminder_message_id")


def downgrade() -> None:
    # Recreate the old columns (NULL-tolerant for the backfill),
    # populate from dispatches, drop the new table.
    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "feedback_email_status",
                sa.Text(),
                nullable=False,
                server_default="not_applicable",
            )
        )
        batch_op.add_column(
            sa.Column("feedback_sent_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(sa.Column("feedback_message_id", sa.Text(), nullable=True))
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
        batch_op.add_column(sa.Column("reminder_message_id", sa.Text(), nullable=True))

    bind = op.get_bind()
    for row in bind.execute(
        sa.text(
            "SELECT signup_id, channel, status, message_id, sent_at "
            "FROM signup_email_dispatches"
        )
    ).fetchall():
        col_status = f"{row[1]}_email_status"
        col_msg_id = f"{row[1]}_message_id"
        col_sent_at = f"{row[1]}_sent_at"
        bind.execute(
            sa.text(
                f"UPDATE signups SET {col_status} = :status, "
                f"{col_msg_id} = :message_id, {col_sent_at} = :sent_at "
                "WHERE id = :signup_id"
            ),
            {
                "status": row[2],
                "message_id": row[3],
                "sent_at": row[4],
                "signup_id": row[0],
            },
        )

    with op.batch_alter_table("signups", schema=None) as batch_op:
        batch_op.create_index(
            "ix_signups_feedback_email_status", ["feedback_email_status"]
        )
        batch_op.create_index(
            "ix_signups_feedback_message_id", ["feedback_message_id"]
        )
        batch_op.create_index(
            "ix_signups_reminder_email_status", ["reminder_email_status"]
        )
        batch_op.create_index(
            "ix_signups_reminder_message_id", ["reminder_message_id"]
        )

    op.drop_index("ix_dispatches_channel_status", "signup_email_dispatches")
    op.drop_index("ix_dispatches_message_id", "signup_email_dispatches")
    op.drop_index(
        "ix_signup_email_dispatches_signup_id", "signup_email_dispatches"
    )
    op.drop_table("signup_email_dispatches")
