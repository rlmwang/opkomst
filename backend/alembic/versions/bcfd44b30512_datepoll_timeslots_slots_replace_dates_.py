"""datepoll timeslots: slots replace dates, note per submission

Revision ID: bcfd44b30512
Revises: f382a112672b
Create Date: 2026-06-14 07:39:06.127284

Generalises a datepoll candidate from a whole date to a slot
``(on_date, start_time, end_time)`` — NULL times = whole-day, so the
old dates-only poll is the degenerate case. ``datepoll_responses``
now points at a slot, and the per-response ``comment`` is replaced by
one ``note`` per submission.

Pre-launch, there is no response data worth migrating (a date-keyed
response has no meaningful slot to map onto), so the two dependent
tables are dropped and recreated rather than altered in place.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bcfd44b30512"
down_revision: str | None = "f382a112672b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the response + candidate tables (responses FK the candidate,
    # so responses go first), then rebuild around slots.
    op.drop_table("datepoll_responses")
    op.drop_table("datepoll_dates")

    op.create_table(
        "datepoll_slots",
        sa.Column("datepoll_id", sa.Text(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["datepoll_id"], ["datepolls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "datepoll_id",
            "on_date",
            "start_time",
            "end_time",
            name="uq_datepoll_slots_poll_slot",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_datepoll_slots_datepoll_id"), "datepoll_slots", ["datepoll_id"], unique=False)

    op.add_column("datepoll_submissions", sa.Column("note", sa.Text(), nullable=True))

    op.create_table(
        "datepoll_responses",
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("datepoll_slot_id", sa.Text(), nullable=False),
        sa.Column("availability", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["datepoll_slot_id"], ["datepoll_slots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["datepoll_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "datepoll_slot_id", name="uq_datepoll_responses_submission_slot"),
        sa.CheckConstraint("availability IN ('yes', 'no', 'maybe')", name="ck_datepoll_responses_availability"),
    )
    op.create_index(op.f("ix_datepoll_responses_submission_id"), "datepoll_responses", ["submission_id"], unique=False)
    op.create_index(
        op.f("ix_datepoll_responses_datepoll_slot_id"), "datepoll_responses", ["datepoll_slot_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("datepoll_responses")
    op.drop_column("datepoll_submissions", "note")
    op.drop_index(op.f("ix_datepoll_slots_datepoll_id"), table_name="datepoll_slots")
    op.drop_table("datepoll_slots")

    op.create_table(
        "datepoll_dates",
        sa.Column("datepoll_id", sa.Text(), nullable=False),
        sa.Column("on_date", sa.Date(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["datepoll_id"], ["datepolls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("datepoll_id", "on_date", name="uq_datepoll_dates_poll_date"),
    )
    op.create_index(op.f("ix_datepoll_dates_datepoll_id"), "datepoll_dates", ["datepoll_id"], unique=False)

    op.create_table(
        "datepoll_responses",
        sa.Column("submission_id", sa.Text(), nullable=False),
        sa.Column("datepoll_date_id", sa.Text(), nullable=False),
        sa.Column("availability", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["datepoll_date_id"], ["datepoll_dates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["datepoll_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "datepoll_date_id", name="uq_datepoll_responses_submission_date"),
        sa.CheckConstraint("availability IN ('yes', 'no', 'maybe')", name="ck_datepoll_responses_availability"),
    )
    op.create_index(op.f("ix_datepoll_responses_submission_id"), "datepoll_responses", ["submission_id"], unique=False)
    op.create_index(
        op.f("ix_datepoll_responses_datepoll_date_id"), "datepoll_responses", ["datepoll_date_id"], unique=False
    )
