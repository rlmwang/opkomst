"""Direct Event-row construction for worker / dispatcher tests.

An ``Event`` is now a definition with a recurrence rule; concrete dates
are ``Occurrence`` rows. ``make_event`` materialises the in-horizon
occurrences (a one-off by default, so ``event.occurrences[0]`` is always
present) so downstream signup/dispatch fixtures have an occurrence to
point at. ``first_occurrence`` is the convenience most tests want.

The slug counter avoids the uuid7-derived collision tests hit when the
clock is frozen.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from backend.models import Chapter, Event, Occurrence, User
from backend.services import event_recurrence
from backend.services.events import now_wallclock

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
        db.add(Chapter(id=chapter_id, name=f"chapter-{chapter_id}", slug=f"chapter-{chapter_id}"))
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
    name_en: str | None = None,
    topic: str | None = None,
    topic_en: str | None = None,
    starts_in: timedelta = timedelta(days=4),
    duration: timedelta = timedelta(hours=2),
    source_enabled: bool = True,
    feedback_enabled: bool = True,
    reminder_enabled: bool = True,
    listed: bool = True,
    locale: str = "nl",
    chapter_id: str | None = None,
    created_by: str | None = None,
    starts_on: date | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    cycle_slots: list[int] | None = None,
    period_weeks: int = 1,
    span_weeks: int | None = None,
    horizon_days: int = 90,
) -> Event:
    """Insert an Event row + materialise its occurrences. Tests work on the
    row state. Defaults to a one-off (``cycle_slots = []``); pass
    ``cycle_slots`` (weekday offsets ``week*7 + weekday``) + ``period_weeks``
    / ``span_weeks`` for a recurring series, or ``horizon_days`` to bound how
    far ahead occurrences materialise. ``starts_on`` / ``start_time`` /
    ``end_time`` default to the ``starts_in`` anchor with a fixed 2h window."""
    anchor = now_wallclock() + starts_in
    _starts_on = starts_on or anchor.date()
    # Default the time of day to the anchor itself so sub-day ``starts_in``
    # offsets (dispatcher window tests) reproduce the exact wall-clock the
    # old single-datetime model stored; callers pin it explicitly otherwise.
    _start_time = start_time if start_time is not None else anchor.time()
    _end_time = end_time if end_time is not None else (anchor + duration).time()
    chapter_id = chapter_id or "chapter-x"
    created_by = created_by or "user-x"
    _ensure_test_chapter(db, chapter_id)
    _ensure_test_user(db, created_by)
    event = Event(
        slug=_unique_slug(),
        name_nl=name,
        name_en=name_en,
        topic_nl=topic,
        topic_en=topic_en,
        location="Test location",
        starts_on=_starts_on,
        start_time=_start_time,
        end_time=_end_time,
        period_weeks=period_weeks,
        cycle_slots=cycle_slots if cycle_slots is not None else [],
        span_weeks=span_weeks,
        horizon_days=horizon_days,
        source_options=["Mond-tot-mond"],
        source_enabled=source_enabled,
        help_options=[],
        feedback_enabled=feedback_enabled,
        reminder_enabled=reminder_enabled,
        listed=listed,
        locale=locale,
        chapter_id=chapter_id,
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    # ``include_past`` so past-dated fixtures (dispatcher / reaper / reconcile
    # tests) materialise their occurrences; production skips past for
    # recurring events.
    event_recurrence.materialise(db, event, now_wallclock(), include_past=True)
    return event


def weekly_slots(starts_on: date) -> list[int]:
    """The single-weekday ``cycle_slots`` for a plain weekly event on
    ``starts_on``'s weekday (period_weeks = 1)."""
    return [starts_on.weekday()]


def first_occurrence(event: Event) -> Occurrence:
    """The event's earliest materialised occurrence. Always present after
    ``make_event`` because the first occurrence is always materialised."""
    return min(event.occurrences, key=lambda o: o.starts_at)
