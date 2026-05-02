"""Coverage for ``backend/routers/chapters.py``.

Chapters are SCD2 today; the R2 refactor will flatten them to
``deleted_at`` soft-delete. These tests pin the user-visible
behaviour of every chapter endpoint so the refactor is
constrained — same response codes, same shape, same archive +
restore semantics.
"""

from __future__ import annotations

from typing import Any


def _create(client: Any, headers: Any, name: str) -> str:
    r = client.post("/api/v1/chapters", headers=headers, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- list ----------------------------------------------------------


def test_list_chapters_returns_active_only_by_default(client, admin_headers, chapter_id):
    _create(client, admin_headers, "Utrecht")
    r = client.get("/api/v1/chapters", headers=admin_headers)
    assert r.status_code == 200
    rows = r.json()
    names = {a["name"] for a in rows}
    assert names == {"Amsterdam", "Utrecht"}
    assert all(a["archived"] is False for a in rows)


def test_list_chapters_with_include_archived(client, admin_headers, chapter_id):
    """When include_archived=true, soft-deleted chapters surface
    too — admin UI uses this to offer restore."""
    other = _create(client, admin_headers, "Den Haag")
    client.delete(f"/api/v1/chapters/{other}", headers=admin_headers)

    r = client.get("/api/v1/chapters?include_archived=true", headers=admin_headers)
    assert r.status_code == 200
    by_name = {a["name"]: a for a in r.json()}
    assert by_name["Amsterdam"]["archived"] is False
    assert by_name["Den Haag"]["archived"] is True


def test_list_chapters_requires_approved_user(client):
    r = client.get("/api/v1/chapters")
    assert r.status_code == 401


# --- create --------------------------------------------------------


def test_create_chapter_happy_path(client, admin_headers):
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Rotterdam"})
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Rotterdam"
    assert body["archived"] is False
    assert body["city"] is None


def test_create_chapter_normalises_whitespace(client, admin_headers):
    r = client.post(
        "/api/v1/chapters",
        headers=admin_headers,
        json={"name": "  Rotterdam   Zuid  "},
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Rotterdam Zuid"


def test_create_chapter_dupe_name_returns_409(client, admin_headers, chapter_id):
    """Case-insensitive + whitespace-collapsed dupe check on
    active chapters."""
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "amsterdam"})
    assert r.status_code == 409


def test_create_chapter_requires_admin(client, organiser_token):
    r = client.post(
        "/api/v1/chapters",
        headers={"Authorization": f"Bearer {organiser_token}"},
        json={"name": "Whatever"},
    )
    assert r.status_code == 403


# --- patch ---------------------------------------------------------


def test_patch_chapter_rename_happy_path(client, admin_headers, chapter_id):
    r = client.patch(
        f"/api/v1/chapters/{chapter_id}",
        headers=admin_headers,
        json={"name": "Amsterdam-West"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Amsterdam-West"


def test_patch_chapter_rename_collision_returns_409(client, admin_headers, chapter_id):
    other = _create(client, admin_headers, "Utrecht")
    r = client.patch(
        f"/api/v1/chapters/{other}",
        headers=admin_headers,
        json={"name": "Amsterdam"},
    )
    assert r.status_code == 409


def test_patch_chapter_set_city(client, admin_headers, chapter_id):
    r = client.patch(
        f"/api/v1/chapters/{chapter_id}",
        headers=admin_headers,
        json={"city": "Amsterdam", "city_lat": 52.37, "city_lon": 4.90},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["city"] == "Amsterdam"
    assert body["city_lat"] == 52.37
    assert body["city_lon"] == 4.90


def test_patch_chapter_clear_city(client, admin_headers, chapter_id):
    """Passing all three city fields as None clears the city tuple."""
    client.patch(
        f"/api/v1/chapters/{chapter_id}",
        headers=admin_headers,
        json={"city": "Amsterdam", "city_lat": 52.37, "city_lon": 4.90},
    )
    r = client.patch(
        f"/api/v1/chapters/{chapter_id}",
        headers=admin_headers,
        json={"city": None, "city_lat": None, "city_lon": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["city"] is None


def test_patch_unknown_chapter_returns_404(client, admin_headers):
    r = client.patch(
        "/api/v1/chapters/no-such",
        headers=admin_headers,
        json={"name": "X"},
    )
    assert r.status_code == 404


# --- usage ---------------------------------------------------------


def test_chapter_usage_counts_users_and_events(client, admin_headers, chapter_id, organiser_headers):
    """``organiser_headers`` is approved into ``chapter_id`` — should
    show up in users count. After creating an event there, that
    counts too."""
    client.post(
        "/api/v1/events",
        headers=organiser_headers,
        json={
            "name": "Demo",
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
    r = client.get(f"/api/v1/chapters/{chapter_id}/usage", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["users"] >= 1
    assert body["events"] >= 1


# --- archive -------------------------------------------------------


def test_archive_chapter_happy_path(client, admin_headers, chapter_id):
    r = client.delete(f"/api/v1/chapters/{chapter_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["archived"] is True


def test_archive_unknown_chapter_returns_404(client, admin_headers):
    r = client.delete("/api/v1/chapters/no-such", headers=admin_headers)
    assert r.status_code == 404


def _delete_chapter(client, chapter_id: str, headers, body: dict | None = None):  # noqa: ANN001
    """``TestClient.delete`` doesn't accept ``json=``; route through
    ``request("DELETE", ..., json=...)`` instead."""
    return client.request(
        "DELETE",
        f"/api/v1/chapters/{chapter_id}",
        headers=headers,
        json=body,
    )


def test_archive_with_user_reassignment(client, admin_headers, chapter_id, organiser_headers):
    """Archive ``chapter_id`` and move its users to ``other``.
    The original membership row stays in storage (so a chapter
    restore brings the user back) but the live projection on
    /me only carries the new chapter — the archived one is
    filtered out by the soft-delete predicate."""
    other = _create(client, admin_headers, "Utrecht")
    r = _delete_chapter(client, chapter_id, admin_headers, {"reassign_users_to": other})
    assert r.status_code == 200
    me = client.get("/api/v1/auth/me", headers=organiser_headers).json()
    chapter_ids = {c["id"] for c in me["chapters"]}
    assert chapter_ids == {other}


def test_archive_with_invalid_reassign_target_returns_400(client, admin_headers, chapter_id):
    r = _delete_chapter(
        client,
        chapter_id,
        admin_headers,
        {"reassign_users_to": "no-such-chapter"},
    )
    assert r.status_code == 400


def test_archive_self_reassign_returns_400(client, admin_headers, chapter_id):
    r = _delete_chapter(client, chapter_id, admin_headers, {"reassign_users_to": chapter_id})
    assert r.status_code == 400


# --- restore -------------------------------------------------------


def test_restore_chapter_happy_path(client, admin_headers, chapter_id):
    other = _create(client, admin_headers, "Den Haag")
    client.delete(f"/api/v1/chapters/{other}", headers=admin_headers)

    r = client.post(f"/api/v1/chapters/{other}/restore", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["archived"] is False


def test_restore_chapter_with_name_collision_returns_409(client, admin_headers):
    """If the archived name has been re-used by an active chapter
    in the meantime, restore must refuse rather than silently
    creating two chapters with the same name."""
    a = _create(client, admin_headers, "Den Haag")
    client.delete(f"/api/v1/chapters/{a}", headers=admin_headers)
    _create(client, admin_headers, "Den Haag")  # active dupe

    r = client.post(f"/api/v1/chapters/{a}/restore", headers=admin_headers)
    assert r.status_code == 409


def test_restore_unknown_chapter_returns_404(client, admin_headers):
    """Restoring an id that doesn't exist at all → 404 (the row
    is missing). Compare with the next test, which is a row that
    exists but isn't archived → 409 (state conflict)."""
    r = client.post("/api/v1/chapters/no-such/restore", headers=admin_headers)
    assert r.status_code == 404
