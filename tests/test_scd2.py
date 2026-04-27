"""SCD2 chain semantics: edits create new versions sharing the same
``entity_id``, slug stays stable, archive + restore work."""


def test_event_id_stable_across_edits(client, organiser_headers):
    payload = {
        "name": "Original",
        "topic": None,
        "location": "Adam",
        "starts_at": "2026-05-01T18:00:00",
        "ends_at": "2026-05-01T20:00:00",
        "source_options": ["Flyer"],
        "questionnaire_enabled": True,
        "locale": "nl",
    }
    r = client.post("/api/v1/events", headers=organiser_headers, json=payload)
    eid = r.json()["id"]
    slug = r.json()["slug"]

    # Edit name + sources
    payload["name"] = "Renamed"
    payload["source_options"] = ["Flyer", "Word"]
    r = client.put(f"/api/v1/events/{eid}", headers=organiser_headers, json=payload)
    assert r.status_code == 200
    assert r.json()["id"] == eid
    assert r.json()["slug"] == slug
    assert r.json()["name"] == "Renamed"


def test_event_slug_stable_across_archive_restore(client, organiser_headers):
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "T",
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "questionnaire_enabled": True,
            "locale": "nl",
        },
    )
    eid = r.json()["id"]
    slug = r.json()["slug"]
    client.post(f"/api/v1/events/{eid}/archive", headers=organiser_headers)
    client.post(f"/api/v1/events/{eid}/restore", headers=organiser_headers)

    from backend.database import SessionLocal
    from backend.models import Event

    db = SessionLocal()
    try:
        rows = db.query(Event).filter(Event.entity_id == eid).all()  # scd2-history-ok: count chain
    finally:
        db.close()
    assert len(rows) == 3
    assert {r.slug for r in rows} == {slug}


def test_signup_event_id_points_at_entity(client, organiser_headers):
    """Signups must point at ``Event.entity_id`` so they survive
    SCD2 updates without orphaning."""
    r = client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "T",
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F"],
            "questionnaire_enabled": True,
            "locale": "nl",
        },
    )
    eid = r.json()["id"]
    slug = r.json()["slug"]
    client.post(
        f"/api/v1/events/by-slug/{slug}/signups",
        json={"display_name": "X", "party_size": 2, "source_choice": "F", "email": None},
    )
    # Edit the event — the signup must still be reachable via stats.
    client.put(
        f"/api/v1/events/{eid}",
        headers=organiser_headers,
        json={
            "name": "T2",
            "topic": None,
            "location": "Adam",
            "starts_at": "2026-05-01T18:00:00",
            "ends_at": "2026-05-01T20:00:00",
            "source_options": ["F", "Word"],
            "questionnaire_enabled": True,
            "locale": "nl",
        },
    )
    r = client.get(f"/api/v1/events/{eid}/stats", headers=organiser_headers)
    assert r.json()["total_signups"] == 1
    assert r.json()["total_attendees"] == 2
