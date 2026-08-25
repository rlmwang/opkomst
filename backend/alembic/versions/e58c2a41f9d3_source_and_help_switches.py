"""the sign-up form's two questions each get a switch

"Hoe heb je ons gevonden?" and "Ik kan helpen met" were always asked.
Each now has its own switch, like the reminder and feedback ones next
to them, and an event that has them off doesn't ask them.

Every existing event asked for a source (the old schema required at
least one option), so that switch starts on. The help question was
already effectively off wherever its list was empty — the public page
skipped the block — so its switch starts on only where there is
something to offer, which is the same event the visitor saw.

The option lists are left exactly as they are: a switched-off question
keeps its answers so switching it back on restores the organiser's own
list.

Revision ID: e58c2a41f9d3
Revises: d41a9c73b5e2
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e58c2a41f9d3"
down_revision: str | None = "d41a9c73b5e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("source_enabled", "help_enabled"):
        op.add_column(
            "events",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    # ``help_options`` is a JSON array; an empty one means the block
    # never rendered, which is what the switch now says out loud.
    op.execute("UPDATE events SET help_enabled = false WHERE json_array_length(help_options::json) = 0")


def downgrade() -> None:
    op.drop_column("events", "help_enabled")
    op.drop_column("events", "source_enabled")
