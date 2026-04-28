"""Helpers for the worker test suites.

Skips the auth/admin/login flow that ``conftest.py`` wires up
because worker tests don't need a logged-in user — they just need
events, signups, and ``signup_email_dispatches`` rows directly in
the DB.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from uuid_utils import uuid7

from backend.models import (
    EmailChannel,
    EmailStatus,
    Event,
    Signup,
    SignupEmailDispatch,
)
from backend.services import encryption

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


def make_signup(
    db: Session,
    event: Event,
    *,
    email: str | None = "alice@example.test",
    feedback: str | bool | None = None,
    reminder: str | bool | None = None,
    display_name: str = "Alice",
) -> Signup:
    """Insert a Signup row plus its dispatch rows.

    ``feedback`` / ``reminder`` accept:

    * ``None`` (default) — derive from ``email`` and the event's
      toggle, mirroring the signups router. ``"pending"`` if the
      channel applies, otherwise no dispatch row.
    * ``False`` — explicitly skip the dispatch row.
    * a status string (``"pending"``, ``"sent"``, ``"failed"``,
      ``"bounced"``, ``"complaint"``) — insert a dispatch row at
      that status.
    """
    if feedback is None:
        feedback = "pending" if email and event.questionnaire_enabled else False
    if reminder is None:
        reminder = "pending" if email and event.reminder_enabled else False

    signup = Signup(
        event_id=event.entity_id,
        display_name=display_name,
        party_size=1,
        source_choice="Mond-tot-mond",
        help_choices=[],
        encrypted_email=encryption.encrypt(email) if email else None,
    )
    db.add(signup)
    db.flush()

    if feedback:
        db.add(
            SignupEmailDispatch(
                signup_id=signup.id,
                channel=EmailChannel.FEEDBACK,
                status=EmailStatus(feedback),
            )
        )
    if reminder:
        db.add(
            SignupEmailDispatch(
                signup_id=signup.id,
                channel=EmailChannel.REMINDER,
                status=EmailStatus(reminder),
            )
        )
    db.flush()
    return signup


def get_dispatch(
    db: Session, signup_id: str, channel: EmailChannel
) -> SignupEmailDispatch | None:
    """Fetch the (signup, channel) dispatch row for assertions
    or in-test mutation (e.g. setting ``message_id`` to simulate
    a partial-send crash)."""
    return (
        db.query(SignupEmailDispatch)
        .filter(
            SignupEmailDispatch.signup_id == signup_id,
            SignupEmailDispatch.channel == channel,
        )
        .first()
    )


def commit(db: Session) -> None:
    """Commit + close the session so the workers' fresh sessions
    see what we wrote."""
    db.commit()
