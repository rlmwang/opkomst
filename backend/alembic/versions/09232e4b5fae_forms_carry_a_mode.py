"""forms carry a mode

The discriminator that lets one set of tables hold both products:
``survey`` today, ``quiz`` next (``docs/design-quizzes.md``). Existing
rows are surveys, which the server default says, and the CHECK is
written by hand because autogenerate does not diff one.

The list index gains ``mode`` at the front: every list query names the
product before it filters anything else.

Revision ID: 09232e4b5fae
Revises: e80bd732f041
Create Date: 2026-08-26 18:09:05.261330
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "09232e4b5fae"
down_revision: str | None = "e80bd732f041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("forms", sa.Column("mode", sa.Text(), server_default="survey", nullable=False))
    op.create_check_constraint("ck_forms_mode", "forms", "mode IN ('survey', 'quiz')")
    op.drop_index(op.f("ix_forms_archived_chapter"), table_name="forms")
    op.create_index("ix_forms_mode_archived_chapter", "forms", ["mode", "archived_at", "chapter_id"], unique=False)


def downgrade() -> None:
    # A quiz is a row this schema cannot describe: without ``mode`` it
    # would read as a questionnaire with an answer key nobody looks at.
    # Deleting is the honest undo, and the cascade takes its questions
    # and submissions with it.
    op.execute("DELETE FROM forms WHERE mode = 'quiz'")
    op.drop_index("ix_forms_mode_archived_chapter", table_name="forms")
    op.create_index(op.f("ix_forms_archived_chapter"), "forms", ["archived_at", "chapter_id"], unique=False)
    op.drop_constraint("ck_forms_mode", "forms", type_="check")
    op.drop_column("forms", "mode")
