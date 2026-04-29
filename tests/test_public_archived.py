"""Public routes on archived events must not leak content.

When an organiser archives an event, every public surface
(``GET /events/by-slug/{slug}`` and friends) returns 404. The
visitor doesn't need to know whether the event was archived or
never existed — both are "not currently public".

Pinned here so a future "include archived for a grace period"
optimisation has to deal with this test.
"""

from typing import Any

from _helpers import commit
from _helpers.events import make_event

from backend.database import SessionLocal
from backend.models import Event
from backend.services import scd2


def _archive(slug: str) -> None:
    """Set ``archived_at`` on the current Event version. Bypasses
    the router so this helper is independent of the auth + admin
    fixtures the rest of the test suite depends on."""
    from datetime import UTC, datetime

    db = SessionLocal()
    try:
        e = scd2.current(db.query(Event)).filter(Event.slug == slug).one()
        e.archived_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def test_get_event_by_slug_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    assert client.get(f"/api/v1/events/by-slug/{e.slug}").status_code == 200
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}")
    assert r.status_code == 404


def test_event_ics_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    assert client.get(f"/api/v1/events/by-slug/{e.slug}/event.ics").status_code == 200
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/event.ics")
    assert r.status_code == 404


def test_qr_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    assert client.get(f"/api/v1/events/by-slug/{e.slug}/qr.png").status_code == 200
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/qr.png")
    assert r.status_code == 404


def test_signup_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    payload = {
        "display_name": "Anon",
        "party_size": 1,
        "source_choice": "Mond-tot-mond",
        "email": None,
    }
    r = client.post(f"/api/v1/events/by-slug/{e.slug}/signups", json=payload)
    assert r.status_code == 201
    _archive(e.slug)
    r = client.post(f"/api/v1/events/by-slug/{e.slug}/signups", json=payload)
    assert r.status_code == 404


def test_feedback_preview_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    assert (
        client.get(f"/api/v1/events/by-slug/{e.slug}/feedback-preview").status_code
        == 200
    )
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/feedback-preview")
    assert r.status_code == 404


def test_email_preview_404s_on_archived(client, db: Any) -> None:
    e = make_event(db)
    commit(db)
    # Live event renders.
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/email-preview/feedback")
    assert r.status_code == 200
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/email-preview/feedback")
    assert r.status_code == 404


def test_unknown_slug_404s(client) -> None:
    """Sanity: an unknown slug also 404s — same response shape as
    archived, so the visitor can't infer existence."""
    assert client.get("/api/v1/events/by-slug/never-existed").status_code == 404
