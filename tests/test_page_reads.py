"""The one read behind a details page.

An organiser opening an event used to cost six requests, five of them
about the same event, and a datepoll four. Each answer was quick and
the waiting was the asking: at eight organisers at once on one worker
the page took a second to paint.

What is proved here is that the one read says the same as the several
it replaced, including which session it opens on: the soonest that has
not ended, and the last that ran when they all have.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _chapter(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _event(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name_nl": "Buurtvergadering",
        "chapter_id": overrides.pop("chapter_id", None) or _chapter(client, headers),
        "location": "Adam",
        "starts_on": "2026-09-01",
        "start_time": "18:00:00",
        "end_time": "20:00:00",
        "source_options": [{"label": "Flyer"}],
        "source_enabled": True,
        "feedback_enabled": True,
        "listed": True,
        "locale": "nl",
        **overrides,
    }
    r = client.post("/api/v1/event", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_event_page_carries_every_part_the_screen_draws(client, organiser_headers):
    event = _event(client, organiser_headers)
    eid = event["id"]
    page = client.get(f"/api/v1/event/{eid}/page", headers=organiser_headers)
    assert page.status_code == 200, page.text
    page = page.json()

    assert page["event"] == client.get(f"/api/v1/event/{eid}", headers=organiser_headers).json()
    assert page["occurrences"]["occurrences"], "an event materialises its first session on save"
    assert page["feedback"]["submission_count"] == 0

    # The day's two panels are the primary session's, and they are the
    # same answer the day switcher gets when it asks for that day.
    occ = page["primary_occurrence_id"]
    assert occ == page["occurrences"]["occurrences"][0]["id"]
    day = f"/api/v1/event/{eid}/occurrences/{occ}"
    assert page["signups"] == client.get(f"{day}/signups", headers=organiser_headers).json()
    assert page["stats"] == client.get(f"{day}/stats", headers=organiser_headers).json()


def test_the_page_opens_on_the_next_session_that_has_not_ended(client, organiser_headers):
    """A weekly series that started a month ago opens on the coming
    session, not on the first one and not on the last."""
    started = date.today() - timedelta(days=28)
    event = _event(
        client,
        organiser_headers,
        starts_on=started.isoformat(),
        period_weeks=1,
        cycle_slots=[started.weekday()],
        span_weeks=8,
    )
    page = client.get(f"/api/v1/event/{event['id']}/page", headers=organiser_headers).json()
    dates = [o["starts_at"][:10] for o in page["occurrences"]["occurrences"]]
    opened = next(o for o in page["occurrences"]["occurrences"] if o["id"] == page["primary_occurrence_id"])
    assert len(dates) > 2
    assert opened["starts_at"][:10] >= date.today().isoformat()
    # And it is the first such one, not just any of them.
    assert opened["starts_at"][:10] == min(d for d in dates if d >= date.today().isoformat())


def test_the_page_opens_on_the_last_session_when_they_are_all_past(client, organiser_headers):
    event = _event(client, organiser_headers, starts_on=(date.today() - timedelta(days=90)).isoformat())
    page = client.get(f"/api/v1/event/{event['id']}/page", headers=organiser_headers).json()
    last = page["occurrences"]["occurrences"][-1]["id"]
    assert page["primary_occurrence_id"] == last


def test_the_page_is_scoped_like_every_other_read(client, admin_headers, organiser_headers):
    other = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"}).json()["id"]
    theirs = _event(client, admin_headers, chapter_id=other)
    assert client.get(f"/api/v1/event/{theirs['id']}/page", headers=organiser_headers).status_code == 404


def _poll(client: Any, headers: Any, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name_nl": "Wanneer kan iedereen?",
        "chapter_id": overrides.pop("chapter_id", None) or _chapter(client, headers),
        "locale": "nl",
        "slots": [{"on_date": "2026-08-01"}, {"on_date": "2026-08-02"}],
        **overrides,
    }
    r = client.post("/api/v1/datepoll", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_the_datepoll_page_carries_every_part_the_screen_draws(client, organiser_headers):
    poll = _poll(client, organiser_headers)
    pid, first = poll["id"], poll["slots"][0]["id"]
    client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={"display_name": "Alex", "answers": [{"datepoll_slot_id": first, "availability": "yes"}]},
    )

    page = client.get(f"/api/v1/datepoll/{pid}/page", headers=organiser_headers)
    assert page.status_code == 200, page.text
    page = page.json()
    assert page["datepoll"] == client.get(f"/api/v1/datepoll/{pid}", headers=organiser_headers).json()
    assert page["summary"]["submission_count"] == 1
    assert page["summary"]["best_slot_id"] == first
    # The grid under the tallies: one row per person, keyed by date.
    assert [(s["display_name"], s["answers"]) for s in page["submissions"]] == [("Alex", {first: "yes"})]


def test_the_datepoll_page_is_scoped_like_every_other_read(client, admin_headers, organiser_headers):
    other = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Rotterdam"}).json()["id"]
    theirs = _poll(client, admin_headers, chapter_id=other)
    assert client.get(f"/api/v1/datepoll/{theirs['id']}/page", headers=organiser_headers).status_code == 404
