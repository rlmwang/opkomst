"""Chapter-scoped datepoll CRUD + organiser reads.

Mirrors ``test_forms_router.py``: create / list / archive / restore /
delete-guard / scoping, plus the list-row projection (no raw dates,
computed ``date_count`` + range) and the summary tallies.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, dates: list[str] | None = None, name: str = "Test poll") -> dict[str, Any]:
    body: dict[str, Any] = {"chapter_id": _chapter_id(client, headers), "name_nl": name, "locale": "nl"}
    if dates is not None:
        body["slots"] = [{"on_date": d} for d in dates]
    r = client.post("/api/v1/datepoll", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_returns_sorted_slots(client, organiser_headers):
    poll = _create(client, organiser_headers, dates=["2026-07-03", "2026-07-01", "2026-07-02"])
    assert [s["on_date"] for s in poll["slots"]] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert poll["date_count"] == 3
    assert poll["first_date"] == "2026-07-01"
    assert poll["last_date"] == "2026-07-03"


def test_list_row_omits_raw_slots_but_carries_summary(client, organiser_headers):
    _create(client, organiser_headers, dates=["2026-07-01", "2026-07-05"])
    rows = client.get("/api/v1/datepoll", headers=organiser_headers).json()["items"]
    assert len(rows) == 1
    row = rows[0]
    assert "slots" not in row
    assert row["date_count"] == 2
    assert row["first_date"] == "2026-07-01"
    assert row["last_date"] == "2026-07-05"


def test_archive_restore_delete_guard(client, organiser_headers):
    poll = _create(client, organiser_headers, dates=["2026-07-01"])
    pid = poll["id"]
    # A live poll is not in the archive, so the delete route cannot find
    # it: archiving first is still the only way to delete one.
    assert client.delete(f"/api/v1/datepoll/{pid}", headers=organiser_headers).status_code == 404
    # Archive → leaves active list, appears on archived list.
    assert client.post(f"/api/v1/datepoll/{pid}/archive", headers=organiser_headers).status_code == 200
    assert client.get("/api/v1/datepoll", headers=organiser_headers).json()["items"] == []
    assert len(client.get("/api/v1/datepoll/archived", headers=organiser_headers).json()["items"]) == 1
    # Now deletable.
    assert client.delete(f"/api/v1/datepoll/{pid}", headers=organiser_headers).status_code == 204
    assert client.get(f"/api/v1/datepoll/{pid}", headers=organiser_headers).status_code == 404


def test_cross_chapter_is_404(client, organiser_headers, admin_headers, db):
    # Admin creates a poll in a fresh chapter the organiser isn't in.
    from backend.models import Chapter

    other = Chapter(name="Other chapter", slug="other-chapter")
    db.add(other)
    db.commit()
    body = {"chapter_id": other.id, "name_nl": "Hidden", "locale": "nl", "slots": []}
    poll = client.post("/api/v1/datepoll", headers=admin_headers, json=body).json()
    # Organiser (not a member of ``other``) gets 404, not 403.
    assert client.get(f"/api/v1/datepoll/{poll['id']}", headers=organiser_headers).status_code == 404


def test_summary_tallies_and_best_slot(client, organiser_headers):
    poll = _create(client, organiser_headers, dates=["2026-07-01", "2026-07-02"])
    d0, d1 = poll["slots"][0]["id"], poll["slots"][1]["id"]
    slug = poll["slug"]
    # Two yes on d0; on d1 one yes and one left blank, which counts as
    # "can't make it".
    client.post(
        f"/api/v1/datepoll/by-slug/{slug}/submit",
        json={
            "answers": [
                {"datepoll_slot_id": d0, "availability": "yes"},
                {"datepoll_slot_id": d1, "availability": "yes"},
            ],
        },
    )
    client.post(
        f"/api/v1/datepoll/by-slug/{slug}/submit",
        json={
            "answers": [
                {"datepoll_slot_id": d0, "availability": "yes"},
            ],
        },
    )
    summary = client.get(f"/api/v1/datepoll/{poll['id']}/page", headers=organiser_headers).json()["summary"]
    assert summary["submission_count"] == 2
    by_id = {s["id"]: s for s in summary["slots"]}
    assert by_id[d0]["yes"] == 2 and by_id[d0]["no"] == 0
    assert by_id[d1]["yes"] == 1 and by_id[d1]["no"] == 1
    assert summary["best_slot_id"] == d0


def test_image_delete_404_when_no_image(client, organiser_headers):
    poll = _create(client, organiser_headers, dates=["2026-09-01"])
    r = client.delete(f"/api/v1/datepoll/{poll['id']}/image", headers=organiser_headers)
    assert r.status_code == 404
