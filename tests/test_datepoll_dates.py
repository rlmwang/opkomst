"""Coverage for the candidate-date diff (``apply_dates``) + the DB
constraints. ``apply_dates`` matches on the natural key ``on_date``:
new dates insert, dates still present are preserved (so their
responses survive an edit), dropped dates cascade their responses.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, dates: list[str]) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "P",
        "locale": "nl",
        "dates": [{"on_date": d} for d in dates],
    }
    r = client.post("/api/v1/datepolls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _put(client: Any, headers: Any, poll: dict[str, Any], dates: list[str]) -> dict[str, Any]:
    body = {
        "chapter_id": poll["chapter_id"],
        "name": poll["name"],
        "locale": poll["locale"],
        "dates": [{"on_date": d} for d in dates],
    }
    r = client.put(f"/api/v1/datepolls/{poll['id']}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_edit_preserves_kept_date_id_and_responses(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-07-01", "2026-07-02"])
    kept_id = next(d["id"] for d in poll["dates"] if d["on_date"] == "2026-07-01")
    # Submit a response on the kept date.
    client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={
            "answers": [{"datepoll_date_id": kept_id, "availability": "yes"}],
        },
    )
    # Edit: drop 07-02, add 07-09; 07-01 stays.
    out = _put(client, organiser_headers, poll, ["2026-07-01", "2026-07-09"])
    kept_after = next(d for d in out["dates"] if d["on_date"] == "2026-07-01")
    assert kept_after["id"] == kept_id  # same row, matched on on_date
    assert {d["on_date"] for d in out["dates"]} == {"2026-07-01", "2026-07-09"}
    # The response on the kept date survived.
    summary = client.get(f"/api/v1/datepolls/{poll['id']}/summary", headers=organiser_headers).json()
    kept_summary = next(d for d in summary["dates"] if d["id"] == kept_id)
    assert kept_summary["yes"] == 1


def test_unique_date_per_poll(db):
    """The DB rejects two rows with the same ``on_date`` on one poll."""
    from datetime import date

    import pytest
    from sqlalchemy.exc import IntegrityError

    from backend.models import Chapter, Datepoll, DatepollDate, User

    user = User(email="dp-uniq@local.dev", name="DP", role="organiser", is_approved=True)
    ch = Chapter(name="C-uniq")
    db.add_all([user, ch])
    db.flush()
    poll = Datepoll(slug="uniqslug", name="P", locale="nl", chapter_id=ch.id, created_by=user.id)
    db.add(poll)
    db.flush()
    db.add_all(
        [
            DatepollDate(datepoll_id=poll.id, on_date=date(2026, 7, 1)),
            DatepollDate(datepoll_id=poll.id, on_date=date(2026, 7, 1)),
        ]
    )
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_check_rejects_bad_availability(db):
    """The ``ck_datepoll_responses_availability`` CHECK backstops the
    tri-state even if a write path skipped schema validation."""
    import pytest
    from sqlalchemy.exc import IntegrityError

    from backend.models import (
        Chapter,
        Datepoll,
        DatepollDate,
        DatepollResponse,
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
    d = DatepollDate(datepoll_id=poll.id, on_date=__import__("datetime").date(2026, 7, 1))
    sub = DatepollSubmission(datepoll_id=poll.id, display_name=None)
    db.add_all([d, sub])
    db.flush()
    db.add(DatepollResponse(submission_id=sub.id, datepoll_date_id=d.id, availability="bogus"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
