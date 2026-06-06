"""Wall-clock semantics for event times.

The organiser types a date+time into the form; that is what we
store and what we display. No timezone math anywhere — see the
docstring on ``Event.starts_at`` for the rationale and the
``services/events.now_wallclock`` helper for the matching "now".
"""

from datetime import datetime, timedelta
from typing import Any

from _helpers import commit
from _helpers.events import make_event
from _helpers.signups import make_signup

from backend.database import SessionLocal
from backend.models import EmailChannel, Event
from backend.services import mail_lifecycle
from backend.services.events import now_wallclock


def test_event_starts_at_persists_as_naive_wall_clock(db: Any) -> None:
    e = make_event(db, starts_in=timedelta(hours=24))
    commit(db)

    fresh = SessionLocal()
    try:
        row = fresh.query(Event).filter_by(id=e.id).first()
        assert row is not None
        assert row.starts_at.tzinfo is None
        assert row.ends_at.tzinfo is None
    finally:
        fresh.close()


def test_event_create_via_http_rejects_tz_aware_isostring(client, organiser_headers) -> None:
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    payload = {
        "name": "Demo",
        "chapter_id": me["chapters"][0]["id"],
        "topic": None,
        "location": "Adam",
        "latitude": None,
        "longitude": None,
        "starts_at": "2026-06-08T18:00:00Z",  # bug-shaped: tz suffix
        "ends_at": "2026-06-08T20:00:00Z",
        "source_options": ["F"],
        "help_options": [],
        "feedback_enabled": True,
        "reminder_enabled": True,
        "locale": "nl",
    }
    r = client.post("/api/v1/events", headers=organiser_headers, json=payload)
    assert r.status_code == 422
    assert "naive" in r.text


def test_reminder_email_shows_the_organiser_typed_time(db: Any, fake_email: Any) -> None:
    """The bug that triggered this rewrite: the reminder email
    used to print event times in UTC, two hours off from the
    wall-clock the organiser typed. With naive storage and naive
    display the HH:MM in the email is literally the input."""
    starts_at = (now_wallclock() + timedelta(hours=24)).replace(minute=0, second=0, microsecond=0)
    e = make_event(db, starts_in=starts_at - now_wallclock())
    # Force a specific wall-clock so the assertion is unambiguous
    # regardless of test-run hour.
    e.starts_at = datetime(2026, 6, 8, 18, 0)
    e.ends_at = datetime(2026, 6, 8, 20, 0)
    make_signup(db, e, email="alice@example.org")
    commit(db)

    # Window predicate uses now_wallclock — push it just before
    # the event so the row is in the 72h window.
    import freezegun

    with freezegun.freeze_time("2026-06-07T10:00:00"):
        n = mail_lifecycle.run_once(EmailChannel.REMINDER)

    assert n == 1
    body = fake_email.sent[0].html_body
    assert "18:00" in body
    assert "20:00" in body
    # Belt and braces: the UTC-shifted variant must not appear.
    assert "16:00" not in body
