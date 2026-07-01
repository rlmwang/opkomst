"""Accountability event log — ``ShiftEvent`` emission + aggregation.

Tick-side events (assigned / missed) are exercised via the service; the
action-side events (completed / deferred / claimed) via the public API,
then read back through the organiser ``/volunteers`` projection.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, ShiftEvent, User, Volunteer
from backend.services import chore_tick
from backend.services import chores as chores_svc

TODAY = date(2026, 1, 5)  # Monday


# --- tick-side (service) ---------------------------------------------


def _orm_roster(db):
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug="rost1",
        name="R",
        created_by=user.id,
        chapter_id=chapter.id,
        starts_on=TODAY,
        commit_horizon_days=28,
        activated_at=datetime.now(UTC),
    )
    db.add(roster)
    db.commit()
    chore = Chore(roster_id=roster.id, name="Bins", ordinal=1, cycle_slots=[2])
    db.add(chore)
    db.commit()
    return roster, chore


def _kinds(db, roster_id) -> dict[str, int]:
    out: dict[str, int] = {}
    for ev in db.query(ShiftEvent).filter(ShiftEvent.roster_id == roster_id).all():
        out[ev.kind] = out.get(ev.kind, 0) + 1
    return out


def test_tick_records_assigned(db):
    roster, chore = _orm_roster(db)
    vol = Volunteer(roster_id=roster.id, display_name="A", edit_token_hash="ha")
    db.add(vol)
    db.commit()
    db.add(Enrollment(volunteer_id=vol.id, chore_id=chore.id))
    db.commit()

    chore_tick.run_tick(db, TODAY)
    db.rollback()
    scheduled = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.status == "scheduled").count()
    assert _kinds(db, roster.id).get("assigned") == scheduled

    summ = {v.id: v for v in chores_svc.volunteer_summaries(db, roster)}
    assert summ[vol.id].assigned == scheduled


def test_tick_records_missed_for_the_holder(db):
    roster, chore = _orm_roster(db)
    vol = Volunteer(roster_id=roster.id, display_name="A", edit_token_hash="hb")
    db.add(vol)
    db.commit()
    db.add(
        Shift(
            chore_id=chore.id, on_date=TODAY - timedelta(days=1), slot_index=0, status="scheduled", volunteer_id=vol.id
        )
    )
    db.commit()

    chore_tick.run_tick(db, TODAY)
    db.rollback()
    assert _kinds(db, roster.id).get("missed") == 1
    summ = {v.id: v for v in chores_svc.volunteer_summaries(db, roster)}
    assert summ[vol.id].missed == 1


def test_unassigned_missed_shift_records_nothing(db):
    # An open shift that passes (no assignee) is nobody's miss.
    roster, chore = _orm_roster(db)
    db.add(Shift(chore_id=chore.id, on_date=TODAY - timedelta(days=1), slot_index=0, status="scheduled"))
    db.commit()
    chore_tick.run_tick(db, TODAY)
    db.rollback()
    assert _kinds(db, roster.id).get("missed") is None


# --- action-side (API) -----------------------------------------------


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _api_roster(client: Any, headers: Any) -> dict[str, Any]:
    r = client.post(
        "/api/v1/chores",
        headers=headers,
        json={
            "chapter_id": _chapter_id(client, headers),
            "name": "R",
            "starts_on": "2026-01-05",
            "chores": [{"name": "Bins", "cycle_slots": [2]}],
        },
    )
    return r.json()


def _enroll(client: Any, slug: str, name: str, cid: str) -> str:
    return client.post(
        f"/api/v1/chores/by-slug/{slug}/enroll",
        json={"display_name": name, "chore_ids": [cid]},
    ).json()["edit_token"]


def _tick(db: Any) -> None:
    for r in db.query(Roster).filter(Roster.activated_at.is_(None)).all():
        r.activated_at = datetime.now(UTC)
    db.flush()
    chore_tick.run_tick(db, date.today())


def _volunteers(client: Any, headers: Any, rid: str) -> dict[str, dict[str, Any]]:
    rows = client.get(f"/api/v1/chores/{rid}/volunteers", headers=headers).json()
    return {r["display_name"]: r for r in rows}


def test_done_records_completed(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    token = _enroll(client, roster["slug"], "Sam", cid)
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{token}").json()["my_shifts"]
    client.post(f"/api/v1/chores/by-token/{token}/shifts/{my[0]['id']}/done")
    assert _volunteers(client, organiser_headers, roster["id"])["Sam"]["completed"] == 1


def test_pass_records_deferred_and_reassigns(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    a = _enroll(client, roster["slug"], "A", cid)
    _enroll(client, roster["slug"], "B", cid)
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{a}").json()["my_shifts"]
    if not my:
        return
    client.post(f"/api/v1/chores/by-token/{a}/shifts/{my[0]['id']}/pass")
    vols = _volunteers(client, organiser_headers, roster["id"])
    assert vols["A"]["deferred"] == 1
    # B picked up the reassigned shift → their assigned count reflects it.
    assert vols["B"]["assigned"] >= 1


def test_claim_records_as_assigned(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _tick(db)  # no volunteers yet → shifts open
    token = _enroll(client, roster["slug"], "Late", cid)
    open_shifts = client.get(f"/api/v1/chores/by-token/{token}").json()["open_shifts"]
    client.post(f"/api/v1/chores/by-token/{token}/shifts/{open_shifts[0]['id']}/claim")
    # A claim counts toward "assigned so far".
    assert _volunteers(client, organiser_headers, roster["id"])["Late"]["assigned"] == 1
