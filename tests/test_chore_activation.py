"""Roster lifecycle + projection reads — activate / rebalance / outlook (task 11)."""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _create(client: Any, headers: Any, **extra: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "R",
        "starts_on": "2026-01-05",
        "chores": [{"name": "Bins", "cycle_slots": [2]}],
        **extra,
    }
    r = client.post("/api/v1/chores", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_created_roster_is_forming(client, organiser_headers):
    roster = _create(client, organiser_headers)
    assert roster["activated_at"] is None


def test_activate_flips_state_and_is_one_way(client, organiser_headers):
    roster = _create(client, organiser_headers)
    rid = roster["id"]
    r = client.post(f"/api/v1/chores/{rid}/activate", headers=organiser_headers)
    assert r.status_code == 200, r.text
    assert r.json()["activated_at"] is not None
    # One-way: a second activate is a conflict.
    assert client.post(f"/api/v1/chores/{rid}/activate", headers=organiser_headers).status_code == 409


def test_activate_pins_the_commit_window(client, organiser_headers):
    roster = _create(client, organiser_headers)
    client.post(f"/api/v1/chores/{roster['id']}/activate", headers=organiser_headers)
    sched = client.get(f"/api/v1/chores/{roster['id']}/schedule", headers=organiser_headers).json()
    # starts_on is in the past, so the near window has pinned (open) shifts.
    assert sched["stats"]["open"] >= 1
    assert len(sched["confirmed"]) >= 1


def test_rebalance_requires_running(client, organiser_headers):
    roster = _create(client, organiser_headers)
    rid = roster["id"]
    assert client.post(f"/api/v1/chores/{rid}/rebalance", headers=organiser_headers).status_code == 409
    client.post(f"/api/v1/chores/{rid}/activate", headers=organiser_headers)
    assert client.post(f"/api/v1/chores/{rid}/rebalance", headers=organiser_headers).status_code == 200


def test_schedule_outlook_projects_beyond_the_window(client, organiser_headers):
    roster = _create(client, organiser_headers)
    client.post(f"/api/v1/chores/{roster['id']}/activate", headers=organiser_headers)
    sched = client.get(f"/api/v1/chores/{roster['id']}/schedule", headers=organiser_headers).json()
    assert sched["outlook_until"] is not None
    assert len(sched["outlook"]) >= 1  # weekly chore projects past the 21-day horizon


def test_commit_horizon_must_be_ge_reminder_days(client, organiser_headers):
    r = client.post(
        "/api/v1/chores",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name": "R",
            "starts_on": "2026-01-05",
            "reminder_days_before": 10,
            "commit_horizon_days": 5,
            "chores": [],
        },
    )
    assert r.status_code == 422
