"""Chapter-scoped chore-roster CRUD + recurrence validation.

Mirrors ``test_datepolls_router.py``: create / list / get / update
(chore reconcile) / archive / restore / delete-guard / scoping, plus
the chores-specific recurrence rules (k>1 needs a Monday anchor;
out-of-range cycle_slots reject on create but clamp on update).
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Bins roster",
        "starts_on": "2026-01-05",
    }
    body.update(overrides)
    return client.post("/api/v1/chores", headers=headers, json=body)


# --- create / read ---------------------------------------------------


def test_create_minimal(client, organiser_headers):
    r = _create(client, organiser_headers, chores=[{"name": "Bins", "cycle_slots": [2, 4]}])
    assert r.status_code == 201, r.text
    roster = r.json()
    assert roster["chore_count"] == 1
    assert roster["volunteer_count"] == 0
    assert roster["period_weeks"] == 1
    assert roster["chores"][0]["cycle_slots"] == [2, 4]
    assert roster["chores"][0]["ordinal"] == 1


def test_list_row_omits_chores_but_carries_counts(client, organiser_headers):
    _create(client, organiser_headers, chores=[{"name": "A", "cycle_slots": [1]}])
    rows = client.get("/api/v1/chores", headers=organiser_headers).json()
    assert len(rows) == 1
    row = rows[0]
    assert "chores" not in row
    assert row["chore_count"] == 1
    assert row["volunteer_count"] == 0
    assert row["period_weeks"] == 1


def test_cycle_slots_deduped_and_sorted(client, organiser_headers):
    r = _create(client, organiser_headers, chores=[{"name": "A", "cycle_slots": [4, 2, 2]}])
    assert r.json()["chores"][0]["cycle_slots"] == [2, 4]


def test_duplicate_chore_emojis_rejected(client, organiser_headers):
    r = _create(
        client,
        organiser_headers,
        chores=[
            {"name": "A", "cycle_slots": [1], "emoji": "🧹"},
            {"name": "B", "cycle_slots": [2], "emoji": "🧹"},
        ],
    )
    assert r.status_code == 422, r.text


def test_distinct_chore_emojis_ok(client, organiser_headers):
    r = _create(
        client,
        organiser_headers,
        chores=[
            {"name": "A", "cycle_slots": [1], "emoji": "🧹"},
            {"name": "B", "cycle_slots": [2], "emoji": "🍳"},
        ],
    )
    assert r.status_code == 201, r.text


# --- recurrence validation -------------------------------------------


def test_biweekly_ok(client, organiser_headers):
    # k=2 needs no anchor input — the cycle derives it from starts_on.
    r = _create(
        client,
        organiser_headers,
        period_weeks=2,
        chores=[{"name": "Bins", "cycle_slots": [2, 9]}],
    )
    assert r.status_code == 201, r.text
    assert r.json()["chores"][0]["cycle_slots"] == [2, 9]


def test_out_of_range_cycle_slots_rejected_on_create(client, organiser_headers):
    # k=1 → valid offsets are 0..6; 7 is out of range.
    r = _create(client, organiser_headers, chores=[{"name": "A", "cycle_slots": [7]}])
    assert r.status_code == 422


# --- update / reconcile ----------------------------------------------


def test_update_reconciles_chores(client, organiser_headers):
    created = _create(
        client,
        organiser_headers,
        chores=[{"name": "A", "cycle_slots": [2]}, {"name": "B", "cycle_slots": [4]}],
    ).json()
    a_id = next(c["id"] for c in created["chores"] if c["name"] == "A")

    body = {
        "chapter_id": created["chapter_id"],
        "name_nl": created["name_nl"],
        "starts_on": created["starts_on"],
        "chores": [
            {"id": a_id, "name": "A2", "cycle_slots": [2]},  # rename existing
            {"name": "C", "cycle_slots": [1]},  # new (B dropped)
        ],
    }
    r = client.put(f"/api/v1/chores/{created['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200, r.text
    chores = r.json()["chores"]
    assert [c["name"] for c in chores] == ["A2", "C"]
    assert [c["ordinal"] for c in chores] == [1, 2]
    # A kept its id (update in place), B is gone.
    assert any(c["id"] == a_id for c in chores)


def test_shrink_k_clamps_out_of_range_slots_on_update(client, organiser_headers):
    created = _create(
        client,
        organiser_headers,
        period_weeks=2,
        chores=[{"name": "X", "cycle_slots": [2, 9]}],
    ).json()
    x_id = created["chores"][0]["id"]

    body = {
        "chapter_id": created["chapter_id"],
        "name_nl": created["name_nl"],
        "starts_on": created["starts_on"],
        "period_weeks": 1,  # shrink k → offset 9 is now out of range
        "chores": [{"id": x_id, "name": "X", "cycle_slots": [2, 9]}],
    }
    r = client.put(f"/api/v1/chores/{created['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["chores"][0]["cycle_slots"] == [2]  # 9 dropped


# --- archive / restore / delete --------------------------------------


def test_archive_restore_delete_flow(client, organiser_headers):
    roster = _create(client, organiser_headers).json()
    rid = roster["id"]

    # Delete a live roster is refused.
    assert client.delete(f"/api/v1/chores/{rid}", headers=organiser_headers).status_code == 409

    assert client.post(f"/api/v1/chores/{rid}/archive", headers=organiser_headers).status_code == 200
    # Now it shows in archived, not active.
    assert client.get("/api/v1/chores", headers=organiser_headers).json() == []
    archived = client.get("/api/v1/chores/archived", headers=organiser_headers).json()
    assert [r["id"] for r in archived] == [rid]

    # Archive again → 409.
    assert client.post(f"/api/v1/chores/{rid}/archive", headers=organiser_headers).status_code == 409

    assert client.post(f"/api/v1/chores/{rid}/restore", headers=organiser_headers).status_code == 200
    # Archive then hard-delete.
    client.post(f"/api/v1/chores/{rid}/archive", headers=organiser_headers)
    assert client.delete(f"/api/v1/chores/{rid}", headers=organiser_headers).status_code == 204
    assert client.get(f"/api/v1/chores/{rid}", headers=organiser_headers).status_code == 404


# --- scoping ---------------------------------------------------------


def test_unknown_roster_is_404(client, organiser_headers):
    assert client.get("/api/v1/chores/nonexistent", headers=organiser_headers).status_code == 404


def test_roster_in_other_chapter_is_404_for_organiser(client, admin_headers, organiser_headers):
    other = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Other chapter"}).json()
    roster = client.post(
        "/api/v1/chores",
        headers=admin_headers,
        json={"chapter_id": other["id"], "name_nl": "Admin roster", "starts_on": "2026-01-05"},
    ).json()
    # Organiser is not a member of "Other chapter" → 404 (not 403).
    assert client.get(f"/api/v1/chores/{roster['id']}", headers=organiser_headers).status_code == 404


def test_accountability_breaks_down_per_chore(client, organiser_headers):
    """The accountability endpoint returns one section per chore (by
    ordinal), each listing only the volunteers enrolled in that chore.
    A freshly enrolled volunteer with no shift yet is ``pending``."""
    roster = _create(
        client,
        organiser_headers,
        chores=[
            {"name": "Bar", "cycle_slots": [4]},
            {"name": "Keuken", "cycle_slots": [4]},
        ],
    ).json()
    bar = roster["chores"][0]
    # Enrol a volunteer in Bar only (public endpoint, no auth).
    client.post(
        f"/api/v1/chores/by-slug/{roster['slug']}/enroll",
        json={"display_name": "Ada", "chore_ids": [bar["id"]]},
    )

    sections = client.get(f"/api/v1/chores/{roster['id']}/accountability", headers=organiser_headers).json()
    assert [s["chore_name"] for s in sections] == ["Bar", "Keuken"]
    by_name = {s["chore_name"]: s for s in sections}
    assert [v["display_name"] for v in by_name["Bar"]["volunteers"]] == ["Ada"]
    assert by_name["Bar"]["volunteers"][0]["pending"] is True
    assert by_name["Keuken"]["volunteers"] == []


def test_calendar_endpoint_returns_per_chore_days(client, organiser_headers):
    """One entry per chore; a running roster's current month carries
    occurrence days, each with at least one assignee slot."""
    roster = _create(client, organiser_headers, chores=[{"name": "Bar", "cycle_slots": [0, 1, 2, 3, 4, 5, 6]}]).json()
    client.post(f"/api/v1/chores/{roster['id']}/activate", headers=organiser_headers)
    cal = client.get(f"/api/v1/chores/{roster['id']}/calendar", headers=organiser_headers).json()
    assert [c["chore_name"] for c in cal] == ["Bar"]
    days = cal[0]["days"]
    assert days and all("tentative" in d and d["assignees"] for d in days)


def test_rebalance_preview_returns_calendar_with_changes(client, organiser_headers):
    """The preview flags the days a rebalance would change (a late enrollee
    filling open shifts) and does not persist them."""
    roster = _create(client, organiser_headers, chores=[{"name": "Bar", "cycle_slots": [0, 1, 2, 3, 4, 5, 6]}]).json()
    client.post(f"/api/v1/chores/{roster['id']}/activate", headers=organiser_headers)  # window pins open
    client.post(
        f"/api/v1/chores/by-slug/{roster['slug']}/enroll",
        json={"display_name": "Ada", "chore_ids": [roster["chores"][0]["id"]]},
    )
    preview = client.get(f"/api/v1/chores/{roster['id']}/rebalance/preview", headers=organiser_headers).json()
    changed = [d for c in preview for d in c["days"] if d["changed"]]
    assert changed
    assert all(any(a["name"] == "Ada" for a in d["assignees"]) for d in changed)
    # Dry run: the live calendar still shows the shifts open.
    cal = client.get(f"/api/v1/chores/{roster['id']}/calendar", headers=organiser_headers).json()
    assert any(a["open"] for c in cal for d in c["days"] for a in d["assignees"])
