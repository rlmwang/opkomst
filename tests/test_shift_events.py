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
from backend.services.chore_assignment import net_credit, summarize_accountability

TODAY = date(2026, 1, 5)  # Monday


# --- pure aggregation (the fold) -------------------------------------


def test_summarize_splits_regular_from_picked_up():
    # A mix: 2 WRH-assigned regulars; a self-claim, a voluntary cover, and
    # an inherited (removal) pickup — all three are "picked up for others".
    events = [
        ("assigned", "v1"),
        ("assigned", "v1"),
        ("claimed", "v1"),
        ("covered", "v1"),
        ("inherited", "v1"),
        ("completed", "v1"),
        ("deferred", "v1"),
        ("missed", "v1"),
    ]
    counts = summarize_accountability(events)["v1"]
    assert counts.regular_turns == 2
    assert counts.picked_up == 3  # claimed + covered + inherited
    assert (counts.completed, counts.deferred, counts.missed) == (1, 1, 1)


def test_inherited_pickup_is_not_a_regular_turn():
    counts = summarize_accountability([("inherited", "v1")])["v1"]
    assert counts.picked_up == 1
    assert counts.regular_turns == 0


def test_summary_and_ledger_read_one_source():
    # The display fold and the favour ledger consume the identical
    # (kind, volunteer_id) stream, so per volunteer the net credit is
    # exactly picked_up minus the negative outcomes.
    events = [
        ("assigned", "v1"),
        ("claimed", "v1"),
        ("covered", "v1"),
        ("inherited", "v1"),
        ("deferred", "v1"),
        ("missed", "v2"),
        ("covered", "v2"),
    ]
    counts = summarize_accountability(events)
    credit = net_credit(events)
    for vid, c in counts.items():
        assert credit.get(vid, 0) == c.picked_up - c.deferred - c.missed


# --- tick-side (service) ---------------------------------------------


def _orm_roster(db):
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C", slug="c")
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
    assert summ[vol.id].regular_turns == scheduled


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


def test_pass_records_deferred_and_opens(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    a = _enroll(client, roster["slug"], "A", cid)
    _enroll(client, roster["slug"], "B", cid)
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{a}").json()["my_shifts"]
    if not my:
        return
    shift_id = my[0]["id"]
    client.post(f"/api/v1/chores/by-token/{a}/shifts/{shift_id}/pass")
    vols = _volunteers(client, organiser_headers, roster["id"])
    assert vols["A"]["deferred"] == 1
    # The shift is opened for anyone to claim, not auto-reassigned.
    page = client.get(f"/api/v1/chores/by-token/{a}").json()
    assert shift_id in [s["id"] for s in page["open_shifts"]]
    assert shift_id not in [s["id"] for s in page["my_shifts"]]


def test_organiser_reassign_scheduled_records_covered(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    a = _enroll(client, roster["slug"], "A", cid)
    b = _enroll(client, roster["slug"], "B", cid)
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{a}").json()["my_shifts"]
    if not my:
        return
    shift_id = my[0]["id"]
    vols = _volunteers(client, organiser_headers, roster["id"])
    r = client.post(
        f"/api/v1/chores/{roster['id']}/shifts/{shift_id}/reassign",
        headers=organiser_headers,
        json={"volunteer_id": vols["B"]["id"]},
    )
    assert r.status_code == 204, r.text
    # B now holds the shift and it counts as picked up for others.
    assert shift_id in [s["id"] for s in client.get(f"/api/v1/chores/by-token/{b}").json()["my_shifts"]]
    assert shift_id not in [s["id"] for s in client.get(f"/api/v1/chores/by-token/{a}").json()["my_shifts"]]
    assert _volunteers(client, organiser_headers, roster["id"])["B"]["picked_up"] == 1


def test_organiser_reassign_open_shift_records_claimed(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _tick(db)  # no volunteers yet → shifts open
    _enroll(client, roster["slug"], "Late", cid)
    open_shifts = client.get(f"/api/v1/chores/{roster['id']}/schedule", headers=organiser_headers).json()["confirmed"]
    open_ids = [s["id"] for s in open_shifts if s["status"] == "open"]
    if not open_ids:
        return
    vols = _volunteers(client, organiser_headers, roster["id"])
    r = client.post(
        f"/api/v1/chores/{roster['id']}/shifts/{open_ids[0]}/reassign",
        headers=organiser_headers,
        json={"volunteer_id": vols["Late"]["id"]},
    )
    assert r.status_code == 204, r.text
    assert _volunteers(client, organiser_headers, roster["id"])["Late"]["picked_up"] == 1


def test_organiser_reassign_rejects_unenrolled_and_done(client, organiser_headers, db):
    from backend.models import Shift

    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    a = _enroll(client, roster["slug"], "A", cid)
    _enroll(client, roster["slug"], "Out", cid)
    _tick(db)
    my = client.get(f"/api/v1/chores/by-token/{a}").json()["my_shifts"]
    if not my:
        return
    shift_id = my[0]["id"]
    vols = _volunteers(client, organiser_headers, roster["id"])
    # Withdraw "Out" from the chore: an unenrolled volunteer can't take it.
    out_token = client.put(
        f"/api/v1/chores/by-token/{_enroll(client, roster['slug'], 'Tmp', cid)}",
        json={"display_name": "Tmp", "chore_ids": [], "email_reminders": False, "email": None},
    )
    assert out_token.status_code == 200
    tmp_id = _volunteers(client, organiser_headers, roster["id"])["Tmp"]["id"]
    r = client.post(
        f"/api/v1/chores/{roster['id']}/shifts/{shift_id}/reassign",
        headers=organiser_headers,
        json={"volunteer_id": tmp_id},
    )
    assert r.status_code == 409
    # A done shift is settled: it can't change hands either.
    db.query(Shift).filter(Shift.id == shift_id).update({"status": "done"})
    db.commit()
    r = client.post(
        f"/api/v1/chores/{roster['id']}/shifts/{shift_id}/reassign",
        headers=organiser_headers,
        json={"volunteer_id": vols["Out"]["id"]},
    )
    assert r.status_code == 409


def test_claim_records_as_picked_up(client, organiser_headers, db):
    roster = _api_roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _tick(db)  # no volunteers yet → shifts open
    token = _enroll(client, roster["slug"], "Late", cid)
    open_shifts = client.get(f"/api/v1/chores/by-token/{token}").json()["open_shifts"]
    client.post(f"/api/v1/chores/by-token/{token}/shifts/{open_shifts[0]['id']}/claim")
    # A self-claim of an open slot is help beyond a WRH-assigned fair share.
    late = _volunteers(client, organiser_headers, roster["id"])["Late"]
    assert late["picked_up"] == 1
    assert late["regular_turns"] == 0
