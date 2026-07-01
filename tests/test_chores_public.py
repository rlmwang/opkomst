"""Public chore enrolment + personal-page flow (no auth, edit-token).

Mirrors the signups/forms public tests: enrol, revisit by token, edit,
leave, plus the archived/unknown guards and the cross-roster chore
rejection. The volunteer-list leak guard lives here too.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _create_roster(client: Any, headers: Any, chores: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "Bins roster",
        "starts_on": "2026-01-05",
        "chores": chores if chores is not None else [{"name": "Bins", "cycle_slots": [2]}],
    }
    r = client.post("/api/v1/chores", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _enroll(client: Any, slug: str, **body: Any) -> Any:
    return client.post(f"/api/v1/chores/by-slug/{slug}/enroll", json=body)


# --- enrol / personal page -------------------------------------------


def test_enroll_without_email(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    r = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[cid])
    assert r.status_code == 200, r.text
    token = r.json()["edit_token"]

    page = client.get(f"/api/v1/chores/by-token/{token}").json()
    assert page["display_name"] == "Sam"
    assert page["enrolled_chore_ids"] == [cid]
    assert page["has_email"] is False
    assert page["email_reminders"] is False
    assert page["my_shifts"] == [] and page["open_shifts"] == []


def test_public_by_slug_shape(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    pub = client.get(f"/api/v1/chores/by-slug/{roster['slug']}").json()
    assert pub["name"] == "Bins roster"
    assert pub["period_weeks"] == 1
    assert len(pub["chores"]) == 1
    # No organiser-only fields leak to the public shape.
    assert "chapter_id" not in pub and "created_at" not in pub


def test_enroll_with_email_and_reminders(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    r = _enroll(
        client,
        roster["slug"],
        display_name="Ada",
        email="ada@local.dev",
        email_reminders=True,
        chore_ids=[cid],
    )
    token = r.json()["edit_token"]
    page = client.get(f"/api/v1/chores/by-token/{token}").json()
    assert page["has_email"] is True
    assert page["email_reminders"] is True


def test_edit_changes_picks(client, organiser_headers):
    roster = _create_roster(
        client,
        organiser_headers,
        chores=[{"name": "A", "cycle_slots": [1]}, {"name": "B", "cycle_slots": [3]}],
    )
    a, b = (c["id"] for c in roster["chores"])
    token = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[a]).json()["edit_token"]

    r = client.put(
        f"/api/v1/chores/by-token/{token}",
        json={"display_name": "Sam", "chore_ids": [b], "email_reminders": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["enrolled_chore_ids"] == [b]


def test_leave_invalidates_token(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    token = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[]).json()["edit_token"]
    assert client.post(f"/api/v1/chores/by-token/{token}/leave").status_code == 204
    # Token no longer resolves.
    assert client.get(f"/api/v1/chores/by-token/{token}").status_code == 404


# --- guards ----------------------------------------------------------


def test_archived_roster_410(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    client.post(f"/api/v1/chores/{roster['id']}/archive", headers=organiser_headers)
    assert client.get(f"/api/v1/chores/by-slug/{roster['slug']}").status_code == 410
    assert _enroll(client, roster["slug"], display_name="X", chore_ids=[]).status_code == 410


def test_unknown_token_404(client):
    assert client.get("/api/v1/chores/by-token/nope").status_code == 404


def test_enroll_into_foreign_chore_rejected(client, organiser_headers):
    roster_a = _create_roster(client, organiser_headers)
    roster_b = _create_roster(client, organiser_headers, chores=[{"name": "B", "cycle_slots": [4]}])
    foreign = roster_b["chores"][0]["id"]
    r = _enroll(client, roster_a["slug"], display_name="X", chore_ids=[foreign])
    assert r.status_code == 400


# --- privacy: organiser volunteer list never leaks PII ---------------


def test_volunteer_list_leak_guard(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _enroll(client, roster["slug"], display_name="Ada", email="ada@local.dev", email_reminders=True, chore_ids=[cid])

    rows = client.get(f"/api/v1/chores/{roster['id']}/volunteers", headers=organiser_headers).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["display_name"] == "Ada"
    assert row["enrolled_chore_ids"] == [cid]
    assert row["load"] == 0
    banned = {"email", "encrypted_email", "edit_token", "edit_token_hash", "token"}
    assert not (banned & set(row.keys())), set(row.keys())
