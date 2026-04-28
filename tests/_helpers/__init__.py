"""Test helpers.

Each module covers one entity domain (events, signups, users, …) and
exposes the make_X / get_X helpers that let a test seed the world in
3–5 lines without going through the auth/admin/login fixture chain.

The session-flush helper ``commit`` is re-exported here for
convenience — most tests `from tests._helpers import commit` and one
or two domain modules.
"""

from sqlalchemy.orm import Session


def commit(db: Session) -> None:
    """Commit so the workers' fresh sessions see what we wrote."""
    db.commit()


__all__ = ["commit"]
