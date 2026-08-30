"""The organiser's lists, one page at a time.

An organisation runs thousands of events and polls with twenty
sign-ups each. The lists used to answer with all of them and let the
browser sort and search what it had been sent: 1,202 events was 511 KB
and 60 ms of building rows nobody drew.

So a list answers with a page, and the sort, the search and the count
are the statement's. What is tested here is what a caller can rely on:
the page holds what it says, the total counts what the search leaves,
and the order is the one the screen used to apply.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def _chapter(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _event(client: Any, headers: Any, name: str, starts_on: date) -> dict[str, Any]:
    r = client.post(
        "/api/v1/event",
        headers=headers,
        json={
            "name_nl": name,
            "chapter_id": _chapter(client, headers),
            "location": "Amsterdam",
            "starts_on": starts_on.isoformat(),
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "Flyer"}],
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_page_holds_what_it_says_and_the_total_counts_them_all(client, organiser_headers):
    for n in range(7):
        _event(client, organiser_headers, f"Avond {n}", date.today() + timedelta(days=n))

    first = client.get("/api/v1/event?per_page=3", headers=organiser_headers).json()
    assert (first["page"], first["per_page"], first["total"]) == (1, 3, 7)
    assert len(first["items"]) == 3

    third = client.get("/api/v1/event?per_page=3&page=3", headers=organiser_headers).json()
    assert len(third["items"]) == 1
    assert third["total"] == 7

    # Every row appears once across the pages, and none is missed.
    seen = []
    for page in (1, 2, 3):
        seen += [
            e["id"]
            for e in client.get(f"/api/v1/event?per_page=3&page={page}", headers=organiser_headers).json()["items"]
        ]
    assert len(seen) == len(set(seen)) == 7


def test_the_search_is_the_statement_s_and_the_total_follows_it(client, organiser_headers):
    _event(client, organiser_headers, "Buurtvergadering", date.today())
    _event(client, organiser_headers, "Scholing", date.today() + timedelta(days=1))
    _event(client, organiser_headers, "Buurtfeest", date.today() + timedelta(days=2))

    found = client.get("/api/v1/event?q=buurt", headers=organiser_headers).json()
    assert found["total"] == 2
    assert {e["name_nl"] for e in found["items"]} == {"Buurtvergadering", "Buurtfeest"}
    # Case-insensitive, and anywhere in the name.
    assert client.get("/api/v1/event?q=FEEST", headers=organiser_headers).json()["total"] == 1
    # The location counts as the name does: it is the other thing the
    # search box used to match on.
    assert client.get("/api/v1/event?q=amsterdam", headers=organiser_headers).json()["total"] == 3
    assert client.get("/api/v1/event?q=niets", headers=organiser_headers).json()["total"] == 0


def test_events_come_back_soonest_first_and_finished_ones_after(client, organiser_headers):
    """The order the dashboard used to apply in the browser: what is
    coming, soonest first, then what has happened, newest back."""
    _event(client, organiser_headers, "Volgende week", date.today() + timedelta(days=7))
    _event(client, organiser_headers, "Morgen", date.today() + timedelta(days=1))
    _event(client, organiser_headers, "Vorige maand", date.today() - timedelta(days=30))
    _event(client, organiser_headers, "Vorig jaar", date.today() - timedelta(days=365))

    names = [e["name_nl"] for e in client.get("/api/v1/event", headers=organiser_headers).json()["items"]]
    assert names == ["Morgen", "Volgende week", "Vorige maand", "Vorig jaar"]


def test_a_page_is_bounded_however_much_is_asked_for(client, organiser_headers):
    """One request cannot ask for the whole table again."""
    assert client.get("/api/v1/event?per_page=1000", headers=organiser_headers).status_code == 422
    assert client.get("/api/v1/event?page=0", headers=organiser_headers).status_code == 422


def test_the_archive_pages_and_searches_the_same_way(client, organiser_headers):
    for n in range(4):
        event = _event(client, organiser_headers, f"Oud {n}", date.today() - timedelta(days=30 + n))
        client.post(f"/api/v1/event/{event['id']}/archive", headers=organiser_headers)

    page = client.get("/api/v1/event/archived?per_page=2", headers=organiser_headers).json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
    assert client.get("/api/v1/event/archived?q=Oud 2", headers=organiser_headers).json()["total"] == 1
