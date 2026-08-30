"""Blank is the refusal: drop the 'no' availability

A datepoll answer had four states, and two of them meant the same
thing to the person filling it in: a blank slot and an explicit "no"
both read as "I can't make it". They were different rows on disk and
the ranking scored them differently. There is one representation now:
a response row exists for a slot somebody can make (``yes`` or
``maybe``), and a slot they can't make has no row.

Existing ``no`` rows carry no information the blank doesn't, so they
go.

Revision ID: e2a7c40f91bd
Revises: c1f7a2e4b830
"""

from alembic import op

revision: str = "e2a7c40f91bd"
down_revision: str | None = "c1f7a2e4b830"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM datepoll_responses WHERE availability = 'no'")
    op.execute("DELETE FROM datepoll_responses_archive WHERE availability = 'no'")
    op.drop_constraint("ck_datepoll_responses_availability", "datepoll_responses", type_="check")
    op.create_check_constraint(
        "ck_datepoll_responses_availability",
        "datepoll_responses",
        "availability IN ('yes', 'maybe')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_datepoll_responses_availability", "datepoll_responses", type_="check")
    op.create_check_constraint(
        "ck_datepoll_responses_availability",
        "datepoll_responses",
        "availability IN ('yes', 'no', 'maybe')",
    )
