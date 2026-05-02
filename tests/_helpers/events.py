"""Direct Event-row construction for worker / dispatcher tests.

The slug counter avoids the uuid7-derived collision tests hit
when the clock is frozen.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.models import Chapter, Event, User

_slug_counter = 0


def _unique_slug() -> str:
    """Tests with a frozen clock can call ``uuid7`` repeatedly and
    get the same time-based prefix, so a slug derived from the id
    collides on the unique-slug constraint. Counter-suffixed slug
    avoids that."""
    global _slug_counter
    _slug_counter += 1
    return f"slug{_slug_counter:06d}"


def _ensure_test_chapter(db: Session, chapter_id: str) -> None:
    """Insert a placeholder Chapter row so the FK on
    ``Event.chapter_id`` resolves. Idempotent."""
    existing = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if existing is None:
        db.add(Chapter(id=chapter_id, name=f"chapter-{chapter_id}"))
        db.flush()


def _ensure_test_user(db: Session, user_id: str) -> None:
    """Insert a placeholder User row so the FK on
    ``Event.created_by`` resolves. Idempotent."""
    existing = db.query(User).filter(User.id == user_id).first()
    if existing is None:
        db.add(
            User(
                id=user_id,
                email=f"{user_id}@example.test",
                name=user_id,
                role="organiser",
                is_approved=True,
            )
        )
        db.flush()


def make_event(
    db: Session,
    *,
    name: str = "Demo",
    starts_in: timedelta = timedelta(days=4),
    duration: timedelta = timedelta(hours=2),
    feedback_enabled: bool = True,
    reminder_enabled: bool = True,
    locale: str = "nl",
    chapter_id: str | None = None,
    created_by: str | None = None,
) -> Event:
    """Insert an Event row directly. Tests work on the row state."""
    now = datetime.now(UTC)
    starts_at = now + starts_in
    chapter_id = chapter_id or "chapter-x"
    created_by = created_by or "user-x"
    _ensure_test_chapter(db, chapter_id)
    _ensure_test_user(db, created_by)
    event = Event(
        slug=_unique_slug(),
        name=name,
        location="Test location",
        starts_at=starts_at,
        ends_at=starts_at + duration,
        source_options=["Mond-tot-mond"],
        help_options=[],
        feedback_enabled=feedback_enabled,
        reminder_enabled=reminder_enabled,
        locale=locale,
        chapter_id=chapter_id,
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    return event
