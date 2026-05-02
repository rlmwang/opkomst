"""Chapter business logic.

Now that ``Chapter`` is a flat table with ``deleted_at``
soft-delete, every helper is a thin SQL wrapper. The two real
rules left:

* **Name normalisation**: collapse whitespace + dedupe case-
  insensitively. Applied on every write so duplicate detection
  isn't fooled by trailing spaces.
* **Restore-collision rule**: an archived chapter named ``X``
  can only be restored if no live chapter is currently named
  ``X``. Prevents the "delete X → create new X → restore old X"
  duplicate-name footgun.

Error contract: writes raise :class:`ChapterNotFound` for missing
rows and :class:`ChapterRuleViolation` for rule violations
(duplicate name, restore collision, invalid reassign target).
The router catches the two and maps to 404 / 409 respectively;
no service helper returns ``None`` to signal "not found".
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Chapter, Event
from . import user_chapters as user_chapters_svc


class ChapterNotFound(Exception):
    """Raised when a chapter id doesn't resolve to a live row."""


class ChapterRuleViolation(Exception):
    """Raised when a write would violate a chapter business rule
    (duplicate name, restore collision). Maps to HTTP 409."""


class ChapterInvalidInput(Exception):
    """Raised when a write request carries an invalid input —
    today this is only invalid reassign targets (unknown id,
    archived chapter, the id being archived). Maps to HTTP 400."""


def normalise_name(name: str) -> str:
    """Strip surrounding whitespace + collapse internal runs to a
    single space. ``" Den   Haag  "`` → ``"Den Haag"``."""
    return " ".join(name.split())


def _live(db: Session):  # noqa: ANN201
    return db.query(Chapter).filter(Chapter.deleted_at.is_(None))


def all_active(db: Session) -> list[Chapter]:
    return _live(db).order_by(Chapter.name).all()


def latest_versions(db: Session, *, include_archived: bool) -> list[Chapter]:
    """List chapters. With ``include_archived=False`` returns live
    only; with ``True`` returns every row (live + soft-deleted)
    so the admin autocomplete can offer restore."""
    q = db.query(Chapter)
    if not include_archived:
        q = q.filter(Chapter.deleted_at.is_(None))
    return sorted(q.all(), key=lambda a: a.name.lower())


def find_by_id(db: Session, chapter_id: str) -> Chapter | None:
    """Live chapter by id, or ``None``. The two read-side helpers
    (``find_by_id``, ``find_any_by_id``) keep the optional return
    because their callers genuinely want to handle the absent
    case (``name_for_id``, the public list endpoint). Writes use
    ``_require_live`` and raise."""
    return _live(db).filter(Chapter.id == chapter_id).first()


def find_any_by_id(db: Session, chapter_id: str) -> Chapter | None:
    """Any chapter (live or soft-deleted) by id."""
    return db.query(Chapter).filter(Chapter.id == chapter_id).first()


def _require_live(db: Session, chapter_id: str) -> Chapter:
    row = find_by_id(db, chapter_id)
    if row is None:
        raise ChapterNotFound(chapter_id)
    return row


def name_for_id(db: Session, chapter_id: str | None) -> str | None:
    """Resolve a chapter id to a display name. Returns the live
    name if the chapter is active, otherwise the soft-deleted
    name (so a user assigned to a deleted chapter still sees a
    label until an admin reassigns them)."""
    if chapter_id is None:
        return None
    row = find_any_by_id(db, chapter_id)
    return row.name if row else None


def name_exists_active(db: Session, name: str, *, exclude_id: str | None = None) -> bool:
    needle = normalise_name(name).lower()
    q = _live(db).filter(func.lower(Chapter.name) == needle)
    if exclude_id is not None:
        q = q.filter(Chapter.id != exclude_id)
    return q.first() is not None


def create(db: Session, *, name: str) -> Chapter:
    chapter = Chapter(name=normalise_name(name))
    db.add(chapter)
    db.flush()
    return chapter


def update(
    db: Session,
    *,
    chapter_id: str,
    name: str | None = None,
    city: str | None = None,
    city_lat: float | None = None,
    city_lon: float | None = None,
    set_city: bool = False,
) -> Chapter:
    """Partial update. Pass only the fields that should change;
    ``set_city=True`` is required to actually write the city
    tuple (which can be ``None``/``None``/``None`` to clear a
    previously-set city). Raises :class:`ChapterNotFound` if the
    id doesn't resolve, :class:`ChapterRuleViolation` if the new
    name collides with another live chapter."""
    row = _require_live(db, chapter_id)
    changes: dict[str, Any] = {}
    if name is not None:
        name = normalise_name(name)
        if name != row.name:
            if name_exists_active(db, name, exclude_id=chapter_id):
                raise ChapterRuleViolation("Name already in use")
            changes["name"] = name
    if set_city:
        changes["city"] = city
        changes["city_lat"] = city_lat
        changes["city_lon"] = city_lon
    for k, v in changes.items():
        setattr(row, k, v)
    db.flush()
    return row


def archive(db: Session, *, chapter_id: str) -> Chapter:
    """Soft-delete: stamp ``deleted_at``. Raises
    :class:`ChapterNotFound` if the id doesn't resolve."""
    row = _require_live(db, chapter_id)
    row.deleted_at = datetime.now(UTC)
    db.flush()
    return row


def archive_with_reassign(
    db: Session,
    *,
    chapter_id: str,
    reassign_users_to: str | None,
    reassign_events_to: str | None,
) -> Chapter:
    """Reassign optional dependents in two bulk UPDATEs, then
    soft-delete the chapter. Both reassignment targets are
    optional — passing ``None`` for either leaves those rows
    pointing at the soon-to-be-archived chapter (they'll go
    invisible / unable-to-act until the chapter is restored).

    Raises :class:`ChapterNotFound` if the chapter doesn't resolve,
    :class:`ChapterRuleViolation` if a reassignment target is
    missing, archived, or the chapter being archived itself."""
    if reassign_users_to == chapter_id or reassign_events_to == chapter_id:
        raise ChapterInvalidInput("Cannot reassign to the chapter being archived")

    if reassign_users_to is not None:
        if find_by_id(db, reassign_users_to) is None:
            raise ChapterInvalidInput("Invalid reassign_users_to target")
        # Add the target chapter to every user currently in the
        # chapter being archived (idempotent; users already in the
        # target are no-ops). The original membership row stays —
        # the chapter's soft-delete hides it at read time, and
        # restoring the chapter brings the relationship back
        # without an admin re-assignment step.
        for user_id in user_chapters_svc.member_user_ids(db, chapter_id):
            user_chapters_svc.add_to_chapter(db, user_id, reassign_users_to)
    if reassign_events_to is not None:
        if find_by_id(db, reassign_events_to) is None:
            raise ChapterInvalidInput("Invalid reassign_events_to target")
        db.query(Event).filter(Event.chapter_id == chapter_id).update(
            {Event.chapter_id: reassign_events_to},
            synchronize_session=False,
        )

    return archive(db, chapter_id=chapter_id)


def restore(db: Session, *, chapter_id: str) -> Chapter:
    """Clear ``deleted_at``. Refuses if the archived name now
    collides (case-insensitive) with another live chapter —
    prevents the duplicate-name footgun. Raises
    :class:`ChapterNotFound` if the id doesn't resolve,
    :class:`ChapterRuleViolation` for the collision."""
    row = find_any_by_id(db, chapter_id)
    if row is None:
        raise ChapterNotFound(chapter_id)
    if row.deleted_at is None:
        raise ChapterRuleViolation("Chapter is already active")
    if name_exists_active(db, row.name):
        raise ChapterRuleViolation(
            f"Name '{row.name}' is already in use by another chapter — rename or delete that one first."
        )
    row.deleted_at = None
    db.flush()
    return row
