"""entities store where their image is, not a URL to it

The column held a ``raw.githubusercontent.com`` URL, which put the
hosting account on every public page and in every email. It now holds
the path inside the image host (``events/{id}/{ts}.jpg``); the URL
anyone sees is the app's own, built at read time.

Existing rows carry the old absolute URLs, so the prefix is stripped
off them here. Anything that doesn't look like one of ours is cleared:
a value we can't turn into a path can't be served, and a null renders
the same as an entity that never had a picture.

Revision ID: d41a9c73b5e2
Revises: c93a17e5b208
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d41a9c73b5e2"
down_revision: str | None = "c93a17e5b208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("events", "forms", "datepolls", "rosters")

# ``https://raw.githubusercontent.com/{owner}/{repo}/{branch}/`` is five
# slash-separated parts before the path we want, and the owner, repo and
# branch are deployment configuration rather than something this
# migration should hard-code. Splitting on the fourth slash after the
# scheme drops exactly that prefix.
_STRIP = r"^https://raw\.githubusercontent\.com/[^/]+/[^/]+/[^/]+/"


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "image_url", new_column_name="image_path")
        op.execute(
            f"""
            UPDATE {table}
               SET image_path = CASE
                   WHEN image_path ~ '{_STRIP}'
                   THEN regexp_replace(image_path, '{_STRIP}', '')
                   ELSE NULL
               END
             WHERE image_path IS NOT NULL
            """
        )


def downgrade() -> None:
    # The prefix is gone and this migration doesn't know the repo it
    # came from, so the rows come back as paths under the old name.
    # Re-uploading is the way back to a working URL.
    for table in _TABLES:
        op.alter_column(table, "image_path", new_column_name="image_url")
