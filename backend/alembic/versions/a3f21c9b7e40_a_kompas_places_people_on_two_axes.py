"""a kompas places people on two axes

The forms table's third product (``docs/design-kompas.md``). Three
changes and no data migration, because no row is a kompas yet.

``compass_axes`` holds exactly two rows per kompas: what each axis is
called, what it is about, and what its two sides are called. The unique key on
``(form_id, axis)`` and the CHECK on the vocabulary are what make
"exactly two" a fact about the schema rather than a habit of the
writer.

``form_questions`` gains the direction an answer moves somebody in. A
rating poles the statement (``pole``, the side a 5 means); a choice
poles each option (``option_poles``, a JSON list parallel to
``options``). Nothing stores a position: an answer plus the current
poles is the position.

And ``ck_forms_mode`` learns the third value.

Revision ID: a3f21c9b7e40
Revises: 27cecb4028b3
Create Date: 2026-08-26 22:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f21c9b7e40"
down_revision: str | None = "27cecb4028b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compass_axes",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("form_id", sa.Text(), nullable=False),
        sa.Column("axis", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("low_name", sa.Text(), nullable=False),
        sa.Column("high_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["forms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("form_id", "axis", name="uq_compass_axes_form_axis"),
        sa.CheckConstraint("axis IN ('x', 'y')", name="ck_compass_axes_axis"),
    )
    op.create_index(op.f("ix_compass_axes_form_id"), "compass_axes", ["form_id"], unique=False)
    op.create_index(op.f("ix_compass_axes_tenant_id"), "compass_axes", ["tenant_id"], unique=False)

    op.add_column("form_questions", sa.Column("pole", sa.Text(), nullable=True))
    op.add_column("form_questions", sa.Column("option_poles", sa.JSON(), nullable=True))

    op.drop_constraint("ck_forms_mode", "forms", type_="check")
    op.create_check_constraint("ck_forms_mode", "forms", "mode IN ('survey', 'quiz', 'compass')")


def downgrade() -> None:
    # A kompas is a row this schema cannot describe: without its axes
    # and its poles it would read as a questionnaire whose answers mean
    # nothing. Deleting is the honest undo, and the cascade takes its
    # questions, submissions and axes with it.
    op.execute("DELETE FROM forms WHERE mode = 'compass'")
    op.drop_constraint("ck_forms_mode", "forms", type_="check")
    op.create_check_constraint("ck_forms_mode", "forms", "mode IN ('survey', 'quiz')")

    op.drop_column("form_questions", "option_poles")
    op.drop_column("form_questions", "pole")

    op.drop_index(op.f("ix_compass_axes_tenant_id"), table_name="compass_axes")
    op.drop_index(op.f("ix_compass_axes_form_id"), table_name="compass_axes")
    op.drop_table("compass_axes")
