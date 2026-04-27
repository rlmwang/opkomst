"""Helpers for the worker test suites.

Skips the auth/admin/login flow that ``conftest.py`` wires up
because worker tests don't need a logged-in user — they just need
events and signups directly in the DB.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from uuid_utils import uuid7

from backend.models import Event, Signup
from backend.services import encryption


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
        slug=eid[:8],
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


def make_signup(
    db: Session,
    event: Event,
    *,
    email: str | None = "alice@example.test",
    feedback_status: str | None = None,
    reminder_status: str | None = None,
    display_name: str = "Alice",
) -> Signup:
    """Insert a Signup row. ``email`` controls the encrypted blob;
    ``*_status`` defaults derive from the event's toggles when
    ``email`` is set, mirroring the router's logic. Pass an
    explicit status to bypass that mapping."""
    if feedback_status is None:
        feedback_status = (
            "pending" if email and event.questionnaire_enabled else "not_applicable"
        )
    if reminder_status is None:
        reminder_status = (
            "pending" if email and event.reminder_enabled else "not_applicable"
        )
    signup = Signup(
        event_id=event.entity_id,
        display_name=display_name,
        party_size=1,
        source_choice="Mond-tot-mond",
        help_choices=[],
        encrypted_email=encryption.encrypt(email) if email else None,
        feedback_email_status=feedback_status,
        reminder_email_status=reminder_status,
    )
    db.add(signup)
    db.flush()
    return signup


def commit(db: Session) -> None:
    """Commit + close the session so the workers' fresh sessions
    see what we wrote."""
    db.commit()
