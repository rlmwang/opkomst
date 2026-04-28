"""Direct Event-row construction for worker / dispatcher tests.

Bypasses the SCD2 helpers — tests work on the row state, not the
history. The slug counter avoids the uuid7-derived collision tests
hit when the clock is frozen.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from uuid_utils import uuid7

from backend.models import Event

_slug_counter = 0


def _unique_slug() -> str:
    """Tests with a frozen clock can call ``uuid7`` repeatedly and
    get the same time-based prefix, so a slug derived from the id
    collides on the unique-slug constraint. Counter-suffixed slug
    avoids that."""
    global _slug_counter
    _slug_counter += 1
    return f"slug{_slug_counter:06d}"


def make_event(
    db: Session,
    *,
    name: str = "Demo",
    starts_in: timedelta = timedelta(days=4),
    duration: timedelta = timedelta(hours=2),
    questionnaire_enabled: bool = True,
    reminder_enabled: bool = True,
    locale: str = "nl",
    chapter_id: str | None = None,
    created_by: str | None = None,
) -> Event:
    """Insert a current-version Event row directly. No SCD2
    tracking churn — tests work on the row state, not history."""
    eid = str(uuid7())
    now = datetime.now(UTC)
    starts_at = now + starts_in
    event = Event(
        id=eid,
        entity_id=eid,
        slug=_unique_slug(),
        name=name,
        location="Test location",
        starts_at=starts_at,
        ends_at=starts_at + duration,
        source_options=["Mond-tot-mond"],
        help_options=[],
        questionnaire_enabled=questionnaire_enabled,
        reminder_enabled=reminder_enabled,
        locale=locale,
        chapter_id=chapter_id or "chapter-x",
        created_by=created_by or "user-x",
        valid_from=now,
        valid_until=None,
        changed_by=created_by or "user-x",
        change_kind="created",
    )
    db.add(event)
    db.flush()
    return event
