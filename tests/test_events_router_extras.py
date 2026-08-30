"""Coverage for the corners of ``backend/routers/events.py`` not
already exercised by ``test_scd2.py``, ``test_email_*``,
``test_public_archived.py``.

Focus: update + archive + restore + email_preview + qr + ics —
the user-visible behaviours the SCD2 collapse must preserve."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.database import SessionLocal
from tests._helpers.events import page_occurrences, public_option_ids


def _first_chapter_id(client: Any, headers: Any) -> str:
    """Pull the caller's first live chapter id from /me. Tests
    that create events through the API need a chapter to assign
    to; the organiser fixture approves the user into exactly one,
    so this resolves deterministically."""
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["chapters"], "test fixture user has no chapters"
    return me["chapters"][0]["id"]


def _next_weekday(weekday: int) -> str:
    """The next date with this weekday, strictly after today. Recurrence
    tests need a start in the future so every session materialises — a
    hardcoded date would silently stop testing that once it went past."""
    today = date.today()
    return (today + timedelta(days=((weekday - today.weekday()) % 7) or 7)).isoformat()


def _new_event(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload = {
        "name_nl": "Demo",
        "chapter_id": _first_chapter_id(client, headers),
        "topic_nl": None,
        "location": "Adam",
        "starts_on": "2026-09-01",
        "start_time": "18:00:00",
        "end_time": "20:00:00",
        "source_options": [{"label": "Flyer"}],
        "source_enabled": True,
        "feedback_enabled": True,
        "reminder_enabled": False,
        "listed": True,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/event", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _first_occurrence(client: Any, headers: Any, event_id: str) -> dict[str, Any]:
    """The event's first materialised occurrence — its public slug is the
    per-occurrence public surface (signups / qr / ics / previews)."""
    return page_occurrences(client, headers, event_id)[0]


def _occ_slug(client: Any, headers: Any, event: dict[str, Any]) -> str:
    return _first_occurrence(client, headers, event["id"])["slug"]


# --- create gating -------------------------------------------------


def test_create_event_missing_chapter_id_returns_422(client, organiser_headers):
    """``chapter_id`` is required on EventCreate — Pydantic
    rejects the body before the handler runs."""
    r = client.post(
        "/api/v1/event",
        headers=organiser_headers,
        json={
            "name_nl": "X",
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "F"}],
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
        "/api/v1/event",
        headers=organiser_headers,
        json={
            "name_nl": "X",
            "chapter_id": other,
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "F"}],
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
        "/api/v1/event",
        headers=admin_headers,
        json={
            "name_nl": "Adminmade",
            "chapter_id": chapter_id,
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "F"}],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text


# --- multi-occurrence booking (one registration, many line items) ----


def test_recurring_signup_creates_one_registration_with_many_line_items(client, organiser_headers):
    """A genuinely recurring event (multiple occurrences) signed up for
    several occurrences in one submission produces exactly one
    ``Registration`` with one ``Signup`` line item per occurrence, plus one
    per-occurrence feedback dispatch — the multi-occurrence sign-up the
    design makes native to the model."""
    # Starts on the coming Saturday (weekday 5); weekly for 3 weeks.
    event = _new_event(
        client,
        organiser_headers,
        name="Boksles",
        starts_on=_next_weekday(5),
        start_time="18:00:00",
        end_time="20:00:00",
        period_weeks=1,
        cycle_slots=[5],
        span_weeks=3,
        feedback_enabled=True,
        reminder_enabled=False,
    )
    occs = page_occurrences(client, organiser_headers, event['id'])
    assert len(occs) == 3  # weekly × 3, all inside the 90-day horizon
    occ_ids = [o["id"] for o in occs]

    ack = client.post(
        f"/api/v1/event/by-slug/{occs[0]['slug']}/signups",
        json={
            "display_name": "Sam",
            "party_size": 2,
            "email": "sam@local.dev",
            "occurrence_ids": occ_ids,  # the explicit multi-id path
        },
    )
    assert ack.status_code == 201, ack.text

    db = SessionLocal()
    try:
        from backend.models import EmailChannel, EmailDispatch, Occurrence, Registration, Signup

        occ_id_set = [o.id for o in db.query(Occurrence).filter(Occurrence.event_id == event["id"]).all()]
        regs = db.query(Registration).filter(Registration.event_id == event["id"]).all()
        assert len(regs) == 1  # one booking header
        assert regs[0].party_size == 2
        line_items = db.query(Signup).filter(Signup.registration_id == regs[0].id).all()
        assert len(line_items) == 3  # one line item per occurrence
        assert sorted(s.occurrence_id for s in line_items) == sorted(occ_ids)
        # One feedback dispatch per occurrence (reminders off).
        dispatches = (
            db.query(EmailDispatch)
            .filter(EmailDispatch.occurrence_id.in_(occ_id_set), EmailDispatch.channel == EmailChannel.FEEDBACK)
            .all()
        )
        assert len(dispatches) == 3
    finally:
        db.close()


def test_finite_event_materialises_all_sessions_past_horizon(client, organiser_headers):
    """A finite course materialises every session up front, even ones beyond
    the 90-day horizon, so "20 sessies" resolves to 20 findable occurrences
    (not a horizon-clipped subset) with nothing left as a projection."""
    # Starts on the coming Monday (weekday 0); weekly for 20 weeks runs
    # ~4.5 months out, well past the default 90-day materialisation horizon.
    event = _new_event(
        client,
        organiser_headers,
        name="Cursus",
        starts_on=_next_weekday(0),
        start_time="18:00:00",
        end_time="20:00:00",
        period_weeks=1,
        cycle_slots=[0],
        span_weeks=20,
    )
    occs = client.get(f"/api/v1/event/{event['id']}/page", headers=organiser_headers).json()["occurrences"]
    assert len(occs["occurrences"]) == 20  # all sessions are real rows
    assert occs["projected"] == []  # a finite event has nothing beyond a horizon
    assert occs["total_sessions"] == 20


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
    rows = client.get("/api/v1/event", headers=organiser_headers).json()["items"]
    ids = {e["id"] for e in rows}
    assert {a["id"], b["id"]} <= ids

    # Filtered by primary: only A.
    rows = client.get(f"/api/v1/event?chapter_id={primary}", headers=organiser_headers).json()["items"]
    ids = {e["id"] for e in rows}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_list_events_filter_by_chapter_outside_set_returns_403(client, admin_headers, organiser_headers):
    """The filter is scope-checked too — asking for a chapter you
    can't see returns 403 rather than a quietly empty list, so
    a misconfigured frontend gets a loud failure."""
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Almere"})
    other = r.json()["id"]
    r = client.get(f"/api/v1/event?chapter_id={other}", headers=organiser_headers)
    assert r.status_code == 403


def test_update_event_to_chapter_outside_users_set_returns_403(client, admin_headers, organiser_headers):
    """Updating an event's chapter is allowed (misclick recovery)
    but only to another chapter in the user's set."""
    event = _new_event(client, organiser_headers)
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Breda"})
    other = r.json()["id"]

    payload = {
        "name_nl": event["name_nl"],
        "chapter_id": other,
        "topic_nl": None,
        "location": event["location"],
        "starts_on": event["starts_on"],
        "start_time": event["start_time"],
        "end_time": event["end_time"],
        "source_options": event["source_options"],
        "feedback_enabled": event["feedback_enabled"],
        "reminder_enabled": event["reminder_enabled"],
        "locale": event["locale"],
    }
    r = client.put(f"/api/v1/event/{event['id']}", headers=organiser_headers, json=payload)
    assert r.status_code == 403


def test_create_event_with_invalid_time_window_returns_400(client, organiser_headers):
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.post(
        "/api/v1/event",
        headers=organiser_headers,
        json={
            "name_nl": "X",
            "chapter_id": me["chapters"][0]["id"],
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "20:00:00",
            "end_time": "18:00:00",  # backwards
            "source_options": [{"label": "F"}],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 422


# --- update --------------------------------------------------------


def test_update_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.put(
        f"/api/v1/event/{event['id']}",
        headers=organiser_headers,
        json={
            "name_nl": "Renamed",
            "name_en": "Renamed",
            "chapter_id": event["chapter_id"],
            "topic_nl": "Updated topic",
            "location": "Utrecht",
            "starts_on": "2026-05-02",
            "start_time": "18:00:00",
            "end_time": "21:00:00",
            "source_options": [{"label": "Flyer"}, {"label": "Word"}],
            "feedback_enabled": False,
            "reminder_enabled": True,
            "locale": "en",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == event["id"]  # entity_id stable across edits
    assert body["slug"] == event["slug"]
    assert body["name_nl"] == "Renamed"
    assert body["topic_nl"] == "Updated topic"
    assert body["locale"] == "en"
    assert body["feedback_enabled"] is False
    assert body["reminder_enabled"] is True


def test_update_event_invalid_time_window_returns_400(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.put(
        f"/api/v1/event/{event['id']}",
        headers=organiser_headers,
        json={
            "name_nl": "Demo",
            "chapter_id": event["chapter_id"],
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "20:00:00",
            "end_time": "18:00:00",
            "source_options": [{"label": "F"}],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 422


def test_update_unknown_event_returns_404(client, organiser_headers):
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    r = client.put(
        "/api/v1/event/no-such",
        headers=organiser_headers,
        json={
            "name_nl": "X",
            "chapter_id": me["chapters"][0]["id"],
            "topic_nl": None,
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "F"}],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 404


# --- archive / restore ---------------------------------------------


def test_archive_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.post(f"/api/v1/event/{event['id']}/archive", headers=organiser_headers)
    assert r.status_code == 200


def test_archiving_twice_is_a_404(client, organiser_headers):
    """Archiving moves the event out of ``events``, so the second call
    has nothing live to find. It used to be a 409 on a row that was
    still there with a date on it."""
    event = _new_event(client, organiser_headers)
    client.post(f"/api/v1/event/{event['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/event/{event['id']}/archive", headers=organiser_headers)
    assert r.status_code == 404


def test_restoring_something_live_is_a_404(client, organiser_headers):
    """Nothing in the archive answers to that id."""
    event = _new_event(client, organiser_headers)
    r = client.post(f"/api/v1/event/{event['id']}/restore", headers=organiser_headers)
    assert r.status_code == 404


def test_restore_archived_event_happy_path(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    client.post(f"/api/v1/event/{event['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/event/{event['id']}/restore", headers=organiser_headers)
    assert r.status_code == 200
    # Lands back on the active list.
    listed = client.get("/api/v1/event", headers=organiser_headers).json()["items"]
    assert any(e["id"] == event["id"] for e in listed)


# --- email_preview -------------------------------------------------


def test_email_preview_reminder_for_disabled_channel_returns_404(client, organiser_headers):
    """Reminder preview on an event with reminder disabled must 404
    — previewing email a visitor will never receive misleads."""
    event = _new_event(client, organiser_headers, reminder_enabled=False)
    slug = _occ_slug(client, organiser_headers, event)
    r = client.get(f"/api/v1/event/by-slug/{slug}/email-preview/reminder")
    assert r.status_code == 404


def test_email_preview_feedback_when_enabled_returns_html(client, organiser_headers):
    event = _new_event(client, organiser_headers, feedback_enabled=True)
    slug = _occ_slug(client, organiser_headers, event)
    r = client.get(f"/api/v1/event/by-slug/{slug}/email-preview/feedback")
    assert r.status_code == 200
    # HTML response — Content-Type is text/html.
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert event["name_nl"] in body


def test_email_preview_unknown_channel_returns_404(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    slug = _occ_slug(client, organiser_headers, event)
    r = client.get(f"/api/v1/event/by-slug/{slug}/email-preview/no-such")
    assert r.status_code == 404


# --- qr / ics ------------------------------------------------------


def test_qr_returns_svg(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    slug = _occ_slug(client, organiser_headers, event)
    r = client.get(f"/api/v1/event/by-slug/{slug}/qr.svg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/svg+xml"
    assert r.content.lstrip().startswith(b"<?xml") or r.content.lstrip().startswith(b"<svg")
    assert b"<svg" in r.content


# --- signup delete -------------------------------------------------


def _public_signup(client, occ_slug: str, *, name: str | None = "Anon") -> dict:
    r = client.post(
        f"/api/v1/event/by-slug/{occ_slug}/signups",
        json={
            "display_name": name,
            "party_size": 1,
            **public_option_ids(client, occ_slug, source="Flyer"),
            "help_choices": [],
            "email": None,
            "all_upcoming": True,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _list_signups(client, headers, event_id: str) -> list[dict]:
    occ = _first_occurrence(client, headers, event_id)
    r = client.get(f"/api/v1/event/{event_id}/occurrences/{occ['id']}/signups", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_delete_signup_removes_only_targeted_row(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    slug = _occ_slug(client, organiser_headers, event)
    _public_signup(client, slug, name="Keep")
    _public_signup(client, slug, name="Remove")

    rows = _list_signups(client, organiser_headers, event["id"])
    assert {r["display_name"] for r in rows} == {"Keep", "Remove"}
    target = next(r for r in rows if r["display_name"] == "Remove")

    r = client.delete(
        f"/api/v1/event/{event['id']}/signups/{target['id']}",
        headers=organiser_headers,
    )
    assert r.status_code == 204

    rows_after = _list_signups(client, organiser_headers, event["id"])
    assert {r["display_name"] for r in rows_after} == {"Keep"}


def test_delete_signup_unknown_id_returns_404(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    r = client.delete(
        f"/api/v1/event/{event['id']}/signups/00000000-0000-0000-0000-000000000000",
        headers=organiser_headers,
    )
    assert r.status_code == 404


def test_delete_signup_requires_auth(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    _public_signup(client, _occ_slug(client, organiser_headers, event))
    rows = _list_signups(client, organiser_headers, event["id"])
    r = client.delete(f"/api/v1/event/{event['id']}/signups/{rows[0]['id']}")
    assert r.status_code in (401, 403)


# --- stats count people --------------------------------------------


def test_stats_breakdowns_count_people_not_bookings(client, organiser_headers):
    """A booking for three that ticked "Opbouwen" is three helpers and
    three people who came via the flyer — the breakdowns add up to
    ``total_attendees``, not to the number of bookings."""
    event = _new_event(
        client,
        organiser_headers,
        source_options=[{"label": "Flyer"}],
        help_options=[{"label": "Opbouwen"}, {"label": "Afbreken"}],
        help_enabled=True,
    )
    occ = _first_occurrence(client, organiser_headers, event["id"])

    for name, size, help_choices in (("Trio", 3, ["Opbouwen"]), ("Solo", 1, ["Opbouwen", "Afbreken"])):
        r = client.post(
            f"/api/v1/event/by-slug/{occ['slug']}/signups",
            json={
                "display_name": name,
                "party_size": size,
                **public_option_ids(client, occ["slug"], source="Flyer", help_labels=tuple(help_choices)),
                "email": None,
                "all_upcoming": True,
            },
        )
        assert r.status_code == 201, r.text

    stats = client.get(
        f"/api/v1/event/{event['id']}/occurrences/{occ['id']}/stats",
        headers=organiser_headers,
    ).json()
    assert stats["total_signups"] == 2
    assert stats["total_attendees"] == 4
    assert stats["by_help"] == {"Opbouwen": 4, "Afbreken": 1}
    assert stats["by_source"] == {"Flyer": 4}


def test_event_ics_carries_uid_and_dates(client, organiser_headers):
    event = _new_event(client, organiser_headers)
    occ = _first_occurrence(client, organiser_headers, event["id"])
    r = client.get(f"/api/v1/event/by-slug/{occ['slug']}/event.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert f"UID:{occ['id']}" in body
    assert "BEGIN:VEVENT" in body
    assert "END:VEVENT" in body
    assert event["name_nl"] in body
    # Caller is meant to import + re-import; cache headers help that
    # flow without serving stale data.
    assert r.headers.get("cache-control", "").startswith("public")
