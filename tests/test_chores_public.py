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
    # Accountability counts are present (all zero pre-tick).
    assert row["regular_turns"] == 0 and row["picked_up"] == 0
    assert row["completed"] == 0 and row["deferred"] == 0 and row["missed"] == 0
    # Freshly enrolled, pre-tick: holds no pinned or past shift → pending.
    assert row["pending"] is True
    banned = {"email", "encrypted_email", "edit_token", "edit_token_hash", "token"}
    assert not (banned & set(row.keys())), set(row.keys())


# --- shift actions (done / pass / cover / claim) --------------------------


def _enrolled_token(client: Any, organiser_headers: Any) -> tuple[dict[str, Any], str, str]:
    """A roster + one enrolled volunteer's token + the chore id."""
    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    token = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[cid]).json()["edit_token"]
    return roster, token, cid


def _tick(db: Any) -> None:
    from datetime import UTC, date, datetime

    from backend.models import Roster
    from backend.services import chore_tick

    # Rosters are created forming; activate any un-started ones so the tick
    # pins their commit window, then run the tick.
    for r in db.query(Roster).filter(Roster.activated_at.is_(None)).all():
        r.activated_at = datetime.now(UTC)
    db.flush()
    chore_tick.run_tick(db, date.today())


def test_mark_shift_done(client, organiser_headers, db):
    roster, token, _ = _enrolled_token(client, organiser_headers)
    _tick(db)
    page = client.get(f"/api/v1/chores/by-token/{token}").json()
    assert page["my_shifts"], "expected at least one assigned shift after the tick"
    shift_id = page["my_shifts"][0]["id"]

    r = client.post(f"/api/v1/chores/by-token/{token}/shifts/{shift_id}/done")
    assert r.status_code == 200, r.text
    # The done shift drops out of upcoming "my_shifts".
    assert shift_id not in [s["id"] for s in r.json()["my_shifts"]]


def test_done_only_by_assignee(client, organiser_headers, db):
    roster, token, cid = _enrolled_token(client, organiser_headers)
    # A second volunteer, not the assignee.
    other = _enroll(client, roster["slug"], display_name="Other", chore_ids=[cid]).json()["edit_token"]
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{token}").json()["my_shifts"]
    # Only run the assertion against a shift the first volunteer owns.
    if not my:
        return
    shift_id = my[0]["id"]
    r = client.post(f"/api/v1/chores/by-token/{other}/shifts/{shift_id}/done")
    assert r.status_code == 403


def test_pass_reassigns_to_someone_else(client, organiser_headers, db):
    roster, token, cid = _enrolled_token(client, organiser_headers)
    other = _enroll(client, roster["slug"], display_name="Other", chore_ids=[cid]).json()["edit_token"]
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{token}").json()["my_shifts"]
    if not my:
        return
    shift_id = my[0]["id"]
    r = client.post(f"/api/v1/chores/by-token/{token}/shifts/{shift_id}/pass")
    assert r.status_code == 200, r.text
    # The bailer no longer holds it.
    assert shift_id not in [s["id"] for s in r.json()["my_shifts"]]
    # The other volunteer now sees it among their shifts.
    other_shifts = client.get(f"/api/v1/chores/by-token/{other}").json()["my_shifts"]
    assert shift_id in [s["id"] for s in other_shifts]


def test_claim_open_shift(client, organiser_headers, db):
    # Enrol a volunteer AFTER the tick so their shifts stay open until claim.
    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _tick(db)  # no volunteers yet → all shifts open
    token = _enroll(client, roster["slug"], display_name="Late", chore_ids=[cid]).json()["edit_token"]

    page = client.get(f"/api/v1/chores/by-token/{token}").json()
    assert page["open_shifts"], "expected claimable open shifts"
    shift_id = page["open_shifts"][0]["id"]
    r = client.post(f"/api/v1/chores/by-token/{token}/shifts/{shift_id}/claim")
    assert r.status_code == 200, r.text
    assert shift_id in [s["id"] for s in r.json()["my_shifts"]]


def test_organiser_schedule_shows_stats_and_upcoming(client, organiser_headers, db):
    roster, token, cid = _enrolled_token(client, organiser_headers)
    _tick(db)
    sched = client.get(f"/api/v1/chores/{roster['id']}/schedule", headers=organiser_headers).json()
    # The sole volunteer takes every future shift; exact count depends on
    # today's weekday, so assert relationships rather than a fixed number.
    assert sched["stats"]["scheduled"] >= 1
    assert sched["stats"]["done"] == 0 and sched["stats"]["missed"] == 0
    assert len(sched["confirmed"]) == sched["stats"]["scheduled"]
    assert {s["assignee_name"] for s in sched["confirmed"]} == {"Sam"}


# --- cover / swap / availability (task 12) ---------------------------


def test_cover_takes_over_and_records_covered(client, organiser_headers, db):
    from backend.models import ShiftEvent

    roster, _token_a, cid = _enrolled_token(client, organiser_headers)  # Sam
    token_b = _enroll(client, roster["slug"], display_name="Bea", chore_ids=[cid]).json()["edit_token"]
    _tick(db)
    cov = client.get(f"/api/v1/chores/by-token/{token_b}").json()["coverable_shifts"]
    if not cov:
        return  # every shift happened to fall to Bea; nothing of Sam's to cover
    sid = cov[0]["id"]
    r = client.post(f"/api/v1/chores/by-token/{token_b}/shifts/{sid}/cover")
    assert r.status_code == 200, r.text
    assert sid in [s["id"] for s in r.json()["my_shifts"]]
    assert db.query(ShiftEvent).filter(ShiftEvent.shift_id == sid, ShiftEvent.kind == "covered").count() == 1


def test_cover_rejects_your_own_shift(client, organiser_headers, db):
    _roster, token, _cid = _enrolled_token(client, organiser_headers)
    _tick(db)
    mine = client.get(f"/api/v1/chores/by-token/{token}").json()["my_shifts"]
    if not mine:
        return
    r = client.post(f"/api/v1/chores/by-token/{token}/shifts/{mine[0]['id']}/cover")
    assert r.status_code == 400


def test_swap_trades_two_confirmed_shifts(client, organiser_headers, db):
    roster, token_a, cid = _enrolled_token(client, organiser_headers)  # Sam
    _enroll(client, roster["slug"], display_name="Bea", chore_ids=[cid]).json()["edit_token"]
    _tick(db)
    page_a = client.get(f"/api/v1/chores/by-token/{token_a}").json()
    mine, theirs = page_a["my_shifts"], page_a["coverable_shifts"]
    if not mine or not theirs:
        return  # need one shift each to trade
    r = client.post(
        f"/api/v1/chores/by-token/{token_a}/swap",
        json={"mine_shift_id": mine[0]["id"], "theirs_shift_id": theirs[0]["id"]},
    )
    assert r.status_code == 200, r.text
    new_mine = [s["id"] for s in r.json()["my_shifts"]]
    assert theirs[0]["id"] in new_mine and mine[0]["id"] not in new_mine


def test_swap_rejects_a_shift_you_dont_hold(client, organiser_headers, db):
    roster, token_a, cid = _enrolled_token(client, organiser_headers)
    _enroll(client, roster["slug"], display_name="Bea", chore_ids=[cid]).json()["edit_token"]
    _tick(db)
    theirs = client.get(f"/api/v1/chores/by-token/{token_a}").json()["coverable_shifts"]
    if not theirs:
        return
    # A tries to swap a shift that is not theirs as `mine`.
    r = client.post(
        f"/api/v1/chores/by-token/{token_a}/swap",
        json={"mine_shift_id": theirs[0]["id"], "theirs_shift_id": theirs[0]["id"]},
    )
    assert r.status_code == 403


def test_availability_excludes_from_new_pins(client, organiser_headers, db):
    from datetime import date, timedelta

    roster = _create_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    token = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[cid]).json()["edit_token"]
    away = {"ranges": [{"start": str(date.today()), "end": str(date.today() + timedelta(days=400))}]}
    r = client.put(f"/api/v1/chores/by-token/{token}/availability", json=away)
    assert r.status_code == 200, r.text
    assert len(r.json()["availability"]) == 1
    _tick(db)  # pins the window; Sam is away, so nothing is assigned to them
    page = client.get(f"/api/v1/chores/by-token/{token}").json()
    assert page["my_shifts"] == []
    assert page["open_shifts"], "shifts still materialise, just unassigned"


def test_availability_rejects_inverted_range(client, organiser_headers):
    roster = _create_roster(client, organiser_headers)
    token = _enroll(client, roster["slug"], display_name="Sam", chore_ids=[]).json()["edit_token"]
    r = client.put(
        f"/api/v1/chores/by-token/{token}/availability",
        json={"ranges": [{"start": "2026-02-01", "end": "2026-01-01"}]},
    )
    assert r.status_code == 422
