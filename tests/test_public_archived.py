"""Public routes on archived events.

When an organiser archives an event:

* ``GET /by-slug/{slug}`` returns the row with ``archived: true``
  so the public page can render a soft "this event has been
  archived" message instead of a generic 404. A visitor with a
  bookmarked link sees what they were looking for and why it's
  gone, rather than wondering if they typed the URL wrong.
* Every other public surface (ICS, QR, previews, signup POST)
  still 404s — there's no point handing out a calendar invite
  for an archived event, and accepting new sign-ups would
  create rows with no path to be sent to.

The unknown-slug case below is the floor: a 404 here matches the
shape ICS/QR/etc. already use, so an attacker can't probe
existence by 404-vs-200.
"""

from typing import Any

from _helpers import commit
from _helpers.events import make_event

from backend.database import SessionLocal
from backend.models import Event


def _archive(slug: str) -> None:
    """Set ``archived_at`` on the current Event version. Bypasses
    the router so this helper is independent of the auth + admin
    fixtures the rest of the test suite depends on."""
    from datetime import UTC, datetime

    db = SessionLocal()
    try:
        e = db.query(Event).filter(Event.slug == slug).one()
        e.archived_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def test_get_event_by_slug_returns_archived_event_with_flag(client, db: Any) -> None:
    """Public ``/by-slug`` keeps returning archived events so the
    page can render a soft "archived" state. The ``archived`` flag
    on the response distinguishes them from live ones."""
    e = make_event(db)
    commit(db)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}")
    assert r.status_code == 200
    assert r.json()["archived"] is False

    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}")
    assert r.status_code == 200
    assert r.json()["archived"] is True


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
    assert client.get(f"/api/v1/events/by-slug/{e.slug}/qr.svg").status_code == 200
    _archive(e.slug)
    r = client.get(f"/api/v1/events/by-slug/{e.slug}/qr.svg")
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
    assert client.get(f"/api/v1/events/by-slug/{e.slug}/feedback-preview").status_code == 200
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
