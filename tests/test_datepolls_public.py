"""Coverage for the public-by-slug datepoll surface: GET the poll
shape, POST submissions, archived/unknown 410s, validation, anonymous
pseudonym, and the shared public-submit rate limit.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, dates: list[str]) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name": "Public poll",
        "locale": "nl",
        "dates": [{"on_date": d} for d in dates],
    }
    r = client.post("/api/v1/datepolls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_public_get_returns_dates(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01", "2026-08-02"])
    r = client.get(f"/api/v1/datepolls/by-slug/{poll['slug']}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Public poll"
    assert [d["on_date"] for d in body["dates"]] == ["2026-08-01", "2026-08-02"]


def test_public_get_unknown_slug_410s(client):
    assert client.get("/api/v1/datepolls/by-slug/nope").status_code == 410


def test_public_get_archived_410s(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01"])
    client.post(f"/api/v1/datepolls/{poll['id']}/archive", headers=organiser_headers)
    assert client.get(f"/api/v1/datepolls/by-slug/{poll['slug']}").status_code == 410


def test_submit_happy_path_returns_edit_token(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01", "2026-08-02"])
    d0 = poll["dates"][0]["id"]
    r = client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={
            "display_name": "Alex",
            "answers": [{"datepoll_date_id": d0, "availability": "yes", "comment": "works for me"}],
        },
    )
    assert r.status_code == 201
    assert r.json()["edit_token"]  # the secret edit-link token, returned once
    subs = client.get(f"/api/v1/datepolls/{poll['id']}/submissions", headers=organiser_headers).json()
    assert len(subs) == 1
    assert subs[0]["display_name"] == "Alex"
    assert subs[0]["answers"][d0] == "yes"
    assert subs[0]["comments"][d0] == "works for me"


def test_submit_unknown_date_400s(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01"])
    r = client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={
            "answers": [{"datepoll_date_id": "not-a-real-id", "availability": "yes"}],
        },
    )
    assert r.status_code == 400


def test_submit_empty_answers_400s(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01"])
    r = client.post(f"/api/v1/datepolls/by-slug/{poll['slug']}/submit", json={"answers": []})
    assert r.status_code == 400


def test_submit_anonymous_stored_as_null(client, organiser_headers):
    poll = _create(client, organiser_headers, ["2026-08-01"])
    d0 = poll["dates"][0]["id"]
    # No display_name → anonymous; whitespace-only also collapses to null.
    client.post(
        f"/api/v1/datepolls/by-slug/{poll['slug']}/submit",
        json={
            "display_name": "   ",
            "answers": [{"datepoll_date_id": d0, "availability": "maybe"}],
        },
    )
    subs = client.get(f"/api/v1/datepolls/{poll['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["display_name"] is None


def test_submit_rate_limit_fires(client, organiser_headers):
    """The shared ``PUBLIC_SUBMIT`` budget (20/hour) caps public
    submits per IP; the 21st within the window 429s."""
    poll = _create(client, organiser_headers, ["2026-08-01"])
    d0 = poll["dates"][0]["id"]
    body = {"answers": [{"datepoll_date_id": d0, "availability": "yes"}]}
    codes = [client.post(f"/api/v1/datepolls/by-slug/{poll['slug']}/submit", json=body).status_code for _ in range(21)]
    assert 429 in codes
