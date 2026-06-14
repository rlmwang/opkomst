"""Coverage for the candidate-slot diff (``apply_slots``) + the DB
constraints. ``apply_slots`` matches on the natural key
``(on_date, start_time, end_time)``: new slots insert, slots still
present are preserved (so their responses survive an edit), dropped
slots cascade their responses. A whole-day slot has NULL times; a
timed slot has both set with ``end > start``.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, slots: list[dict[str, Any]]) -> dict[str, Any]:
    body = {"chapter_id": _chapter_id(client, headers), "name": "P", "locale": "nl", "slots": slots}
    r = client.post("/api/v1/datepolls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _put(client: Any, headers: Any, poll: dict[str, Any], slots: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "chapter_id": poll["chapter_id"],
        "name": poll["name"],
        "locale": poll["locale"],
        "slots": slots,
    }
    r = client.put(f"/api/v1/datepolls/{poll['id']}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_edit_preserves_kept_slot_id_and_responses(client, organiser_headers):
    poll = _create(client, organiser_headers, [{"on_date": "2026-07-01"}, {"on_date": "2026-07-02"}])
    kept_id = next(s["id"] for s in poll["slots"] if s["on_date"] == "2026-07-01")
    # Submit a response on the kept slot.
    client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={"answers": [{"datepoll_slot_id": kept_id, "availability": "yes"}]},
    )
    # Edit: drop 07-02, add 07-09; 07-01 stays.
    out = _put(client, organiser_headers, poll, [{"on_date": "2026-07-01"}, {"on_date": "2026-07-09"}])
    kept_after = next(s for s in out["slots"] if s["on_date"] == "2026-07-01")
    assert kept_after["id"] == kept_id  # same row, matched on the natural key
    assert {s["on_date"] for s in out["slots"]} == {"2026-07-01", "2026-07-09"}
    # The response on the kept slot survived.
    summary = client.get(f"/api/v1/datepolls/{poll['id']}/summary", headers=organiser_headers).json()
    kept_summary = next(s for s in summary["slots"] if s["id"] == kept_id)
    assert kept_summary["yes"] == 1


def test_timed_slots_roundtrip_and_order(client, organiser_headers):
    """A day can carry whole-day + timed slots; they come back sorted
    by date, whole-day first, then by start time."""
    poll = _create(
        client,
        organiser_headers,
        [
            {"on_date": "2026-07-01", "start_time": "19:00", "end_time": "21:00"},
            {"on_date": "2026-07-01", "start_time": "09:00", "end_time": "12:00"},
            {"on_date": "2026-07-02"},  # whole-day
        ],
    )
    slots = poll["slots"]
    # 07-01 timed slots sort 09:00 before 19:00; 07-02 whole-day after.
    assert [(s["on_date"], s["start_time"]) for s in slots] == [
        ("2026-07-01", "09:00:00"),
        ("2026-07-01", "19:00:00"),
        ("2026-07-02", None),
    ]
    assert slots[2]["end_time"] is None
    # date_count counts distinct days, not slots.
    assert poll["date_count"] == 2


def test_rejects_inverted_time_range(client, organiser_headers):
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name": "P",
        "locale": "nl",
        "slots": [{"on_date": "2026-07-01", "start_time": "21:00", "end_time": "19:00"}],
    }
    assert client.post("/api/v1/datepolls", headers=organiser_headers, json=body).status_code == 422


def test_rejects_half_open_range(client, organiser_headers):
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name": "P",
        "locale": "nl",
        "slots": [{"on_date": "2026-07-01", "start_time": "19:00"}],  # end missing
    }
    assert client.post("/api/v1/datepolls", headers=organiser_headers, json=body).status_code == 422


def test_unique_slot_per_poll(db):
    """The DB rejects two identical slots on one poll — including two
    whole-day slots on the same date (``NULLS NOT DISTINCT``)."""
    from datetime import date, time

    import pytest
    from sqlalchemy.exc import IntegrityError

    from backend.models import Chapter, Datepoll, DatepollSlot, User

    user = User(email="dp-uniq@local.dev", name="DP", role="organiser", is_approved=True)
    ch = Chapter(name="C-uniq")
    db.add_all([user, ch])
    db.flush()
    poll = Datepoll(slug="uniqslug", name="P", locale="nl", chapter_id=ch.id, created_by=user.id)
    db.add(poll)
    db.flush()
    db.add_all(
        [
            DatepollSlot(datepoll_id=poll.id, on_date=date(2026, 7, 1)),
            DatepollSlot(datepoll_id=poll.id, on_date=date(2026, 7, 1)),  # same whole-day slot
        ]
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()

    # Two identical timed slots also collide.
    db.add_all(
        [
            DatepollSlot(datepoll_id=poll.id, on_date=date(2026, 7, 2), start_time=time(19), end_time=time(21)),
            DatepollSlot(datepoll_id=poll.id, on_date=date(2026, 7, 2), start_time=time(19), end_time=time(21)),
        ]
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_check_rejects_bad_availability(db):
    """The ``ck_datepoll_responses_availability`` CHECK backstops the
    tri-state even if a write path skipped schema validation."""
    from datetime import date

    import pytest
    from sqlalchemy.exc import IntegrityError

    from backend.models import (
        Chapter,
        Datepoll,
        DatepollResponse,
        DatepollSlot,
        DatepollSubmission,
        User,
    )

    user = User(email="dp-check@local.dev", name="DP", role="organiser", is_approved=True)
    ch = Chapter(name="C-check")
    db.add_all([user, ch])
    db.flush()
    poll = Datepoll(slug="checkslug", name="P", locale="nl", chapter_id=ch.id, created_by=user.id)
    db.add(poll)
    db.flush()
    s = DatepollSlot(datepoll_id=poll.id, on_date=date(2026, 7, 1))
    sub = DatepollSubmission(datepoll_id=poll.id, display_name=None)
    db.add_all([s, sub])
    db.flush()
    db.add(DatepollResponse(submission_id=sub.id, datepoll_slot_id=s.id, availability="bogus"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
