"""User ↔ chapter membership mutations.

Two helpers consumed by the admin router:

* ``set_chapters(user, chapter_ids)`` — replace the user's
  membership set, returning the (added, removed) diff for the
  audit log. Idempotent at the row level via ``ON CONFLICT
  DO NOTHING`` on the composite PK; concurrent calls converge.
* ``add_to_chapter(user, chapter_id)`` — single-row helper used
  by ``archive_with_reassign``. Race-safe via ``IntegrityError``
  fallback (composite-PK collision means the row is already
  there, so the caller's intent — "user is in chapter X" — holds).

Validation (chapter exists + is live) is the caller's job; this
module trusts the ids it receives.
"""

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..models import User, UserChapter


def current_chapter_ids(db: Session, user_id: str) -> set[str]:
    """All chapter ids the user has a membership row for, regardless
    of the chapter's soft-delete state. The set-chapters diff
    operates on the storage-level state, not the live-filtered view."""
    rows = db.query(UserChapter.chapter_id).filter(UserChapter.user_id == user_id).all()
    return {row[0] for row in rows}


def set_chapters(db: Session, user: User, chapter_ids: list[str]) -> tuple[set[str], set[str]]:
    """Replace the user's membership set with ``chapter_ids``.
    Returns ``(added, removed)`` so the caller can log the audit
    diff. The caller commits."""
    desired = set(chapter_ids)
    existing = current_chapter_ids(db, user.id)
    added = desired - existing
    removed = existing - desired

    if added:
        # ``ON CONFLICT DO NOTHING`` keeps the operation idempotent
        # under concurrent calls — two admins clicking Save at the
        # same moment can't trip a PK violation.
        stmt = pg_insert(UserChapter).values([{"user_id": user.id, "chapter_id": cid} for cid in added])
        stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "chapter_id"])
        db.execute(stmt)

    if removed:
        db.query(UserChapter).filter(
            UserChapter.user_id == user.id,
            UserChapter.chapter_id.in_(removed),
        ).delete(synchronize_session=False)

    return added, removed


def add_to_chapter(db: Session, user_id: str, chapter_id: str) -> None:
    """Idempotent insert of one membership row. Used by the
    chapter-archive reassignment flow."""
    stmt = (
        pg_insert(UserChapter)
        .values(user_id=user_id, chapter_id=chapter_id)
        .on_conflict_do_nothing(index_elements=["user_id", "chapter_id"])
    )
    db.execute(stmt)


def member_user_ids(db: Session, chapter_id: str) -> list[str]:
    """All user ids that have a membership row in this chapter,
    regardless of the user's soft-delete state. Caller filters as
    needed."""
    rows = db.query(UserChapter.user_id).filter(UserChapter.chapter_id == chapter_id).all()
    return [row[0] for row in rows]
