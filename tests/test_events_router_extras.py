"""Coverage for the corners of ``backend/routers/events.py`` not
already exercised by ``test_scd2.py``, ``test_email_*``,
``test_public_archived.py``.

Focus: update + archive + restore + email_preview + qr + ics —
the user-visible behaviours the SCD2 collapse must preserve."""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal


def _first_chapter_id(client: Any, headers: Any) -> str:
    """Pull the caller's first live chapter id from /me. Tests
    that create events through the API need a chapter to assign
    to; the organiser fixture approves the user into exactly one,
    so this resolves deterministically."""
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["chapters"], "test fixture user has no chapters"
    return me["chapters"][0]["id"]


def _new_event(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name": "Demo",
        "chapter_id": _first_chapter_id(client, headers),
        "topic": None,
        "location": "Adam",
        "starts_at": "2026-05-01T18:00:00",
        "ends_at": "2026-05-01T20:00:00",
        "source_options": ["Flyer"],
        "feedback_enabled": True,
        "reminder_enabled": False,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/events", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --- create gating -------------------------------------------------


def test_create_event_missing_chapter_id_returns_422(client, organiser_headers):
    """``chapter_id`` is required on EventCreate — Pydantic
    rejects the body before the handler runs."""
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "X",
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 422


def test_create_event_with_chapter_outside_users_set_returns_403(client, admin_headers, organiser_headers):
    """The chapter_id in the request body must be one the caller
    is a member of. The frontend's dropdown already scopes the
    options; this is the defence-in-depth check."""
    # Create a fresh chapter the organiser is NOT a member of.
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Eindhoven"})
    other = r.json()["id"]

    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "X",
            "chapter_id": other,
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 403


def test_create_event_with_admin_globally_works(client, admin_headers):
    """Admins are global — they implicitly belong to every live
    chapter and can create events anywhere. The bootstrap admin
    isn't approved-into a chapter via /approve; this guards
    against a regression where the admin-as-organiser path 403s
    its own chapters."""
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Groningen"})
    chapter_id = r.json()["id"]
    r = client.post(
        "/api/v1/events",
        headers=admin_headers,
        json={
            "name": "Adminmade",
            "chapter_id": chapter_id,
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text


def test_list_events_filter_by_chapter(client, admin_headers, organiser_headers):
    """``?chapter_id=…`` narrows the list to that one chapter,
    even when the organiser is a member of several."""
    # Add a second chapter to the organiser via /set-chapters.
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Rotterdam"})
    other = r.json()["id"]

    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    primary = me["chapters"][0]["id"]
    # /me reflects the organiser's own user; we need their UID.
    db = SessionLocal()
    try:
        from backend.models import User

        user = db.query(User).filter(User.email == "organiser@local.dev", User.deleted_at.is_(None)).first()
        assert user is not None
        uid = user.id
    finally:
        db.close()
    client.post(
        f"/api/v1/admin/users/{uid}/set-chapters",
        headers=admin_headers,
        json={"chapter_ids": [primary, other]},
    )

    a = _new_event(client, organiser_headers, name="A", chapter_id=primary)
    b = _new_event(client, organiser_headers, name="B", chapter_id=other)

    # No filter: both events.
    rows = client.get("/api/v1/events", headers=organiser_headers).json()
    ids = {e["id"] for e in rows}
    assert {a["id"], b["id"]} <= ids

    # Filtered by primary: only A.
    rows = client.get(f"/api/v1/events?chapter_id={primary}", headers=organiser_headers).json()
    ids = {e["id"] for e in rows}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_list_events_filter_by_chapter_outside_set_returns_403(client, admin_headers, organiser_headers):
    """The filter is scope-checked too — asking for a chapter you
    can't see returns 403 rather than a quietly empty list, so
    a misconfigured frontend gets a loud failure."""
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Almere"})
    other = r.json()["id"]
    r = client.get(f"/api/v1/events?chapter_id={other}", headers=organiser_headers)
    assert r.status_code == 403


def test_update_event_to_chapter_outside_users_set_returns_403(client, admin_headers, organiser_headers):
    """Updating an event's chapter is allowed (misclick recovery)
    but only to another chapter in the user's set."""
    event = _new_event(client, organiser_headers)
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Breda"})
    other = r.json()["id"]

    payload = {
        "name": event["name"],
        "chapter_id": other,
        "topic": None,
        "location": event["location"],
        "starts_at": event["starts_at"],
        "ends_at": event["ends_at"],
        "source_options": event["source_options"],
        "feedback_enabled": event["feedback_enabled"],
        "reminder_enabled": event["reminder_enabled"],
        "locale": event["locale"],
    }
    r = client.put(f"/api/v1/events/{event['id']}", headers=organiser_headers, json=payload)
    assert r.status_code == 403


def test_create_event_with_invalid_time_window_returns_400(client, organiser_headers):
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "X",
            "chapter_id": me["chapters"][0]["id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T20:00:00",
            "ends_at": "2026-05-01T18:00:00",  # backwards
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 400


# --- update --------------------------------------------------------


def test_update_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.put(
        f"/api/v1/events/{event['id']}",
        headers=organiser_headers,
        json={
            "name": "Renamed",
            "chapter_id": event["chapter_id"],
            "topic": "Updated topic",
            "location": "Utrecht",
            "starts_at": "2026-05-02T18:00:00",
            "ends_at": "2026-05-02T21:00:00",
            "source_options": ["Flyer", "Word"],
            "feedback_enabled": False,
            "reminder_enabled": True,
            "locale": "en",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == event["id"]  # entity_id stable across edits
    assert body["slug"] == event["slug"]
    assert body["name"] == "Renamed"
    assert body["topic"] == "Updated topic"
    assert body["locale"] == "en"
    assert body["feedback_enabled"] is False
    assert body["reminder_enabled"] is True


def test_update_event_invalid_time_window_returns_400(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.put(
        f"/api/v1/events/{event['id']}",
        headers=organiser_headers,
        json={
            "name": "Demo",
            "chapter_id": event["chapter_id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T20:00:00",
            "ends_at": "2026-05-01T18:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 400


def test_update_unknown_event_returns_404(client, organiser_headers):
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.put(
        "/api/v1/events/no-such",
        headers=organiser_headers,
        json={
            "name": "X",
            "chapter_id": me["chapters"][0]["id"],
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 404


# --- archive / restore ---------------------------------------------


def test_archive_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.post(f"/api/v1/events/{event['id']}/archive", headers=organiser_headers)
    assert r.status_code == 200


def test_archive_already_archived_returns_409(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    client.post(f"/api/v1/events/{event['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/events/{event['id']}/archive", headers=organiser_headers)
    assert r.status_code == 409


def test_restore_not_archived_returns_409(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.post(f"/api/v1/events/{event['id']}/restore", headers=organiser_headers)
    assert r.status_code == 409


def test_restore_archived_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    client.post(f"/api/v1/events/{event['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/events/{event['id']}/restore", headers=organiser_headers)
    assert r.status_code == 200
    # Lands back on the active list.
    listed = client.get("/api/v1/events", headers=organiser_headers).json()
    assert any(e["id"] == event["id"] for e in listed)


# --- email_preview -------------------------------------------------


def test_email_preview_reminder_for_disabled_channel_returns_404(client, organiser_headers):
    """Reminder preview on an event with reminder disabled must 404
    — previewing email a visitor will never receive misleads."""
    event = _new_event(client, organiser_headers, reminder_enabled=False)
    r = client.get(f"/api/v1/events/by-slug/{event['slug']}/email-preview/reminder")
    assert r.status_code == 404


def test_email_preview_feedback_when_enabled_returns_html(client, organiser_headers):
    event = _new_event(client, organiser_headers, feedback_enabled=True)
    r = client.get(f"/api/v1/events/by-slug/{event['slug']}/email-preview/feedback")
    assert r.status_code == 200
    # HTML response — Content-Type is text/html.
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert event["name"] in body


def test_email_preview_unknown_channel_returns_404(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.get(f"/api/v1/events/by-slug/{event['slug']}/email-preview/no-such")
    assert r.status_code == 404


# --- qr / ics ------------------------------------------------------


def test_qr_returns_svg(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.get(f"/api/v1/events/by-slug/{event['slug']}/qr.svg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/svg+xml"
    assert r.content.lstrip().startswith(b"<?xml") or r.content.lstrip().startswith(b"<svg")
    assert b"<svg" in r.content


# --- signup delete -------------------------------------------------


def _public_signup(client, slug: str, *, name: str | None = "Anon") -> dict:
    r = client.post(
        f"/api/v1/events/by-slug/{slug}/signups",
        json={
            "display_name": name,
            "party_size": 1,
            "source_choice": "Flyer",
            "help_choices": [],
            "email": None,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _list_signups(client, headers, event_id: str) -> list[dict]:
    r = client.get(f"/api/v1/events/{event_id}/signups", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_delete_signup_removes_only_targeted_row(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    _public_signup(client, event["slug"], name="Keep")
    _public_signup(client, event["slug"], name="Remove")

    rows = _list_signups(client, organiser_headers, event["id"])
    assert {r["display_name"] for r in rows} == {"Keep", "Remove"}
    target = next(r for r in rows if r["display_name"] == "Remove")

    r = client.delete(
        f"/api/v1/events/{event['id']}/signups/{target['id']}",
        headers=organiser_headers,
    )
    assert r.status_code == 204

    rows_after = _list_signups(client, organiser_headers, event["id"])
    assert {r["display_name"] for r in rows_after} == {"Keep"}


def test_delete_signup_unknown_id_returns_404(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.delete(
        f"/api/v1/events/{event['id']}/signups/00000000-0000-0000-0000-000000000000",
        headers=organiser_headers,
    )
    assert r.status_code == 404


def test_delete_signup_requires_auth(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    _public_signup(client, event["slug"])
    rows = _list_signups(client, organiser_headers, event["id"])
    r = client.delete(f"/api/v1/events/{event['id']}/signups/{rows[0]['id']}")
    assert r.status_code in (401, 403)


def test_event_ics_carries_uid_and_dates(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.get(f"/api/v1/events/by-slug/{event['slug']}/event.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert f"UID:{event['id']}" in body
    assert "BEGIN:VEVENT" in body
    assert "END:VEVENT" in body
    assert event["name"] in body
    # Caller is meant to import + re-import; cache headers help that
    # flow without serving stale data.
    assert r.headers.get("cache-control", "").startswith("public")
