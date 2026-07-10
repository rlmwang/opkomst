"""bilingual title and description

Revision ID: 6023884ff187
Revises: 4f000956b809
Create Date: 2026-07-10 19:57:32.206654
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6023884ff187"
down_revision: str | None = "4f000956b809"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _split_bilingual(table: str, body: str) -> None:
    """Add the ``name_*`` + ``{body}_*`` pair, backfill the existing single
    column into the slot matching each row's primary ``locale`` (so the old
    content survives and the name-present check holds), then drop the old
    columns."""
    op.add_column(table, sa.Column("name_nl", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("name_en", sa.Text(), nullable=True))
    op.add_column(table, sa.Column(f"{body}_nl", sa.Text(), nullable=True))
    op.add_column(table, sa.Column(f"{body}_en", sa.Text(), nullable=True))
    op.execute(
        f"UPDATE {table} SET "
        "name_nl = CASE WHEN locale = 'en' THEN NULL ELSE name END, "
        "name_en = CASE WHEN locale = 'en' THEN name ELSE NULL END, "
        f"{body}_nl = CASE WHEN locale = 'en' THEN NULL ELSE {body} END, "
        f"{body}_en = CASE WHEN locale = 'en' THEN {body} ELSE NULL END"
    )
    op.drop_column(table, "name")
    op.drop_column(table, body)


def upgrade() -> None:
    _split_bilingual("events", "topic")
    _split_bilingual("datepolls", "description")
    _split_bilingual("forms", "description")
    _split_bilingual("rosters", "description")

    # Recipient locale, captured at sign-up / join, drives per-recipient email
    # language. New NOT NULL column with a server default so existing rows fill.
    op.add_column("email_dispatches", sa.Column("locale", sa.Text(), server_default=sa.text("'nl'"), nullable=False))
    op.add_column("volunteers", sa.Column("locale", sa.Text(), server_default=sa.text("'nl'"), nullable=False))

    # At least one language of the title must be set (the primary-language
    # one is required at the schema boundary). Raw-SQL check, so autogenerate
    # can't diff it — added and dropped by hand.
    for table in ("events", "datepolls", "forms", "rosters"):
        op.create_check_constraint(f"ck_{table}_name_present", table, "num_nonnulls(name_nl, name_en) >= 1")


def _merge_bilingual(table: str, body: str) -> None:
    """Reverse of ``_split_bilingual``: re-add the single ``name`` + ``body``
    columns, collapse the pair back into them (preferring whichever language
    is set), restore ``name`` NOT NULL, then drop the ``*_nl`` / ``*_en``
    pair."""
    op.add_column(table, sa.Column("name", sa.Text(), nullable=True))
    op.add_column(table, sa.Column(body, sa.Text(), nullable=True))
    op.execute(f"UPDATE {table} SET name = COALESCE(name_nl, name_en), {body} = COALESCE({body}_nl, {body}_en)")
    op.alter_column(table, "name", nullable=False)
    op.drop_column(table, "name_nl")
    op.drop_column(table, "name_en")
    op.drop_column(table, f"{body}_nl")
    op.drop_column(table, f"{body}_en")


def downgrade() -> None:
    for table in ("events", "datepolls", "forms", "rosters"):
        op.drop_constraint(f"ck_{table}_name_present", table, type_="check")
    op.drop_column("volunteers", "locale")
    op.drop_column("email_dispatches", "locale")
    _merge_bilingual("events", "topic")
    _merge_bilingual("datepolls", "description")
    _merge_bilingual("forms", "description")
    _merge_bilingual("rosters", "description")
