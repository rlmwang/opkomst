"""Membership change — addition fold-in + removal re-cover (task 13).

Joining never rewrites a promise; leaving rewrites only the leaver's own
pinned shifts (re-covered as an ``inherited`` pickup, or opened if nobody
is eligible). The frozen past is untouched.
"""

from datetime import UTC, date, datetime

from backend.models import Chapter, Chore, Enrollment, Roster, Shift, ShiftEvent, User, Volunteer
from backend.services import chore_tick
from backend.services import chores as chores_svc

TODAY = date(2026, 1, 5)  # a Monday


def _roster(db):
    user = User(email="o@local.dev", name="O", role="organiser", is_approved=True)
    chapter = Chapter(name="C", slug="c")
    db.add_all([user, chapter])
    db.commit()
    roster = Roster(
        slug="rm1",
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


def _volunteer(db, roster, chore, name):
    vol = Volunteer(roster_id=roster.id, display_name=name, edit_token_hash=f"h-{name}")
    db.add(vol)
    db.commit()
    db.add(Enrollment(volunteer_id=vol.id, chore_id=chore.id))
    db.commit()
    return vol


def _future_scheduled(db, chore_id):
    return (
        db.query(Shift)
        .filter(Shift.chore_id == chore_id, Shift.on_date >= TODAY, Shift.status == "scheduled")
        .all()
    )


def test_newcomer_is_pending_until_folded_in(db):
    roster, chore = _roster(db)
    _volunteer(db, roster, chore, "A")
    chore_tick.run_tick(db, TODAY)  # A gets pinned shifts
    _volunteer(db, roster, chore, "B")  # enrols after the window is pinned
    summ = {v.display_name: v for v in chores_svc.volunteer_summaries(db, roster)}
    assert summ["A"].pending is False
    assert summ["B"].pending is True


def test_addition_does_not_disturb_existing_pins(db):
    roster, chore = _roster(db)
    a = _volunteer(db, roster, chore, "A")
    chore_tick.run_tick(db, TODAY)
    before = sorted(s.id for s in _future_scheduled(db, chore.id) if s.volunteer_id == a.id)
    assert before, "A should hold pinned shifts"
    _volunteer(db, roster, chore, "B")
    chore_tick.run_tick(db, TODAY)  # B is not folded into the already-pinned window
    after = sorted(s.id for s in _future_scheduled(db, chore.id) if s.volunteer_id == a.id)
    assert after == before  # A's promises stand


def test_removal_recovers_leavers_pins_to_the_remaining(db):
    roster, chore = _roster(db)
    a = _volunteer(db, roster, chore, "A")
    b = _volunteer(db, roster, chore, "B")
    chore_tick.run_tick(db, TODAY)
    db.delete(a)
    db.flush()  # SET NULL orphans A's future shifts
    chore_tick.cover_orphaned_shifts(db, roster.id, TODAY)
    db.commit()
    future = _future_scheduled(db, chore.id)
    assert future and all(s.volunteer_id == b.id for s in future)  # B inherits them
    assert db.query(ShiftEvent).filter(ShiftEvent.roster_id == roster.id, ShiftEvent.kind == "inherited").count() >= 1


def test_removal_with_no_eligible_opens_the_shifts(db):
    roster, chore = _roster(db)
    a = _volunteer(db, roster, chore, "A")
    chore_tick.run_tick(db, TODAY)
    db.delete(a)
    db.flush()
    chore_tick.cover_orphaned_shifts(db, roster.id, TODAY)
    db.commit()
    assert _future_scheduled(db, chore.id) == []  # nothing left scheduled
    opens = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date >= TODAY, Shift.status == "open").all()
    assert opens and all(s.volunteer_id is None for s in opens)


def test_removal_leaves_the_frozen_past_untouched(db):
    roster, chore = _roster(db)
    a = _volunteer(db, roster, chore, "A")
    db.add(
        Shift(
            chore_id=chore.id,
            on_date=date(2025, 12, 31),
            slot_index=0,
            status="done",
            volunteer_id=a.id,
            done_at=datetime(2025, 12, 31, tzinfo=UTC),
        )
    )
    db.commit()
    db.delete(a)
    db.flush()
    chore_tick.cover_orphaned_shifts(db, roster.id, TODAY)
    db.commit()
    past = db.query(Shift).filter(Shift.chore_id == chore.id, Shift.on_date == date(2025, 12, 31)).one()
    assert past.status == "done"  # completed history is preserved


def test_leave_endpoint_recovers_shifts(client, organiser_headers, db):
    from datetime import date as _date

    cid_header = client.get("/api/v1/auth/me", headers=organiser_headers).json()["chapters"][0]["id"]
    roster = client.post(
        "/api/v1/chores",
        headers=organiser_headers,
        json={
            "chapter_id": cid_header,
            "name": "R",
            "starts_on": "2026-01-05",
            "chores": [{"name": "Bins", "cycle_slots": [2]}],
        },
    ).json()
    slug, cid = roster["slug"], roster["chores"][0]["id"]
    ta = client.post(f"/api/v1/chores/by-slug/{slug}/enroll", json={"display_name": "A", "chore_ids": [cid]}).json()[
        "edit_token"
    ]
    client.post(f"/api/v1/chores/by-slug/{slug}/enroll", json={"display_name": "B", "chore_ids": [cid]})
    for r in db.query(Roster).filter(Roster.activated_at.is_(None)).all():
        r.activated_at = datetime.now(UTC)
    db.flush()
    chore_tick.run_tick(db, _date.today())
    # A leaves → their shifts must not linger unassigned.
    assert client.post(f"/api/v1/chores/by-token/{ta}/leave").status_code == 204
    orphaned = (
        db.query(Shift)
        .join(Chore, Chore.id == Shift.chore_id)
        .filter(
            Chore.roster_id == roster["id"],
            Shift.on_date >= _date.today(),
            Shift.volunteer_id.is_(None),
            Shift.status == "scheduled",
        )
        .count()
    )
    assert orphaned == 0
