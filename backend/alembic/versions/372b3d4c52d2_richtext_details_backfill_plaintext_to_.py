"""richtext details backfill plaintext to html

Revision ID: 372b3d4c52d2
Revises: 160bd9d63fe3
Create Date: 2026-07-08 11:47:03.188621

The four organiser-authored "details" bodies (event ``topic``, form /
datepoll / roster ``description``) become sanitized rich-text HTML and
are rendered with ``v-html`` on the public pages. Existing rows were
authored in a *plaintext* textarea, so they must be converted to safe
HTML before that switch: escape every character and turn paragraph /
line breaks into ``<p>`` / ``<br>``. Escaping (not tag-stripping) is
correct because the old content was literal text, and it is what makes
any stray ``<script>`` a harmless ``&lt;script&gt;`` under ``v-html``.

Self-contained (no app import) so it stays frozen. Idempotent: rows that
already contain markup are skipped.
"""

import html as _html
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "372b3d4c52d2"
down_revision: str | None = "160bd9d63fe3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column) for the four rich-text bodies. Per-chore descriptions
# on ``chores`` stay plain text and are not touched.
_TARGETS = [
    ("events", "topic"),
    ("forms", "description"),
    ("datepolls", "description"),
    ("rosters", "description"),
]


def _plaintext_to_html(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    parts: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        escaped = _html.escape(para.strip()).replace("\n", "<br>")
        if escaped:
            parts.append(f"<p>{escaped}</p>")
    return "".join(parts) or None


def upgrade() -> None:
    conn = op.get_bind()
    for table, column in _TARGETS:
        rows = conn.execute(
            sa.text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")
        ).fetchall()
        for row_id, value in rows:
            # Skip anything that already looks like markup (idempotent).
            if value is None or "</" in value or "<br" in value:
                continue
            converted = _plaintext_to_html(value)
            conn.execute(
                sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
                {"v": converted, "id": row_id},
            )


def downgrade() -> None:
    # One-way data conversion; the column type is unchanged, and the
    # stored HTML still renders acceptably as text if the app reverts.
    pass
