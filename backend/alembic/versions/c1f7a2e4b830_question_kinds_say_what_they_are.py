"""Question kinds say what the app calls them

The two choice kinds were named the wrong way round against the
product's own words: ``single_choice`` was the kind every screen calls
Meerkeuze / Multiple choice, and ``multi_choice`` the one they call
Meerdere antwoorden / Multiple answer. Somebody reading the code had to
translate, and the kompas' rules read as their own opposite.

They are now ``multiple_choice`` (pick one) and ``multiple_answer``
(pick several), which is what the editor, the public page and the
locales already said.

Revision ID: c1f7a2e4b830
Revises: 9e905c01a135
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c1f7a2e4b830"
down_revision: str | Sequence[str] | None = "9e905c01a135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = "kind IN ('rating', 'text', 'short_text', 'single_choice', 'multi_choice', 'number')"
_NEW = "kind IN ('rating', 'text', 'short_text', 'multiple_choice', 'multiple_answer', 'number')"


def _rename(table: str, before: str, after: str) -> None:
    op.execute(f"UPDATE {table} SET kind = '{after}' WHERE kind = '{before}'")


def upgrade() -> None:
    # The archive twin holds the same values and carries no CHECK of its
    # own, so it is renamed and not re-constrained.
    op.drop_constraint("ck_form_questions_kind", "form_questions", type_="check")
    for table in ("form_questions", "form_questions_archive"):
        _rename(table, "single_choice", "multiple_choice")
        _rename(table, "multi_choice", "multiple_answer")
    op.create_check_constraint("ck_form_questions_kind", "form_questions", _NEW)


def downgrade() -> None:
    op.drop_constraint("ck_form_questions_kind", "form_questions", type_="check")
    for table in ("form_questions", "form_questions_archive"):
        _rename(table, "multiple_choice", "single_choice")
        _rename(table, "multiple_answer", "multi_choice")
    op.create_check_constraint("ck_form_questions_kind", "form_questions", _OLD)
