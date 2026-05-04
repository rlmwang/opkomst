"""Coverage for the new-members feedback survey router.

Submit-and-aggregate happy path, validation of required ratings,
unknown barrier rejection, admin-only gate on the results
endpoint, and that ``first_name`` round-trips so an organiser can
follow up with a respondent.
"""

from __future__ import annotations

from typing import Any


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "first_name": "Sam",
        "q1_connected": 4,
        "q2_clarity": 2,
        "q3_likelihood": 3,
        "q4_barriers": ["no_time", "no_clear_step"],
        "q4_other_text": None,
        "q5_helps": "Een buddy om mee te lopen.",
    }
    base.update(overrides)
    return base


def test_form_endpoint_lists_barrier_keys(client: Any) -> None:
    r = client.get("/api/v1/member-survey/form")
    assert r.status_code == 200
    body = r.json()
    assert "no_time" in body["barriers"]
    assert "nobody_asked" in body["barriers"]
    assert len(body["barriers"]) == 8


def test_submit_then_results_round_trip(client: Any, admin_headers: Any) -> None:
    r = client.post("/api/v1/member-survey/responses", json=_payload())
    assert r.status_code == 201, r.text

    r = client.post(
        "/api/v1/member-survey/responses",
        json=_payload(
            first_name=None,
            q1_connected=2,
            q2_clarity=2,
            q3_likelihood=2,
            q4_barriers=["nobody_asked"],
            q5_helps=None,
        ),
    )
    assert r.status_code == 201

    r = client.get("/api/v1/member-survey/results", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["response_count"] == 2
    # q1 average: (4 + 2) / 2 == 3.0
    assert body["q1_connected"]["average"] == 3.0
    assert body["q1_connected"]["distribution"] == [0, 1, 0, 1, 0]
    assert body["barrier_counts"]["no_time"] == 1
    assert body["barrier_counts"]["nobody_asked"] == 1
    assert body["barrier_counts"]["doubts_impact"] == 0
    # First-name round-trip — organisers need it to follow up.
    names = sorted(r.get("first_name") or "" for r in body["responses"])
    assert names == ["", "Sam"]


def test_results_admin_only(client: Any, organiser_headers: Any) -> None:
    """Approved organisers don't see results — admin-only."""
    r = client.get("/api/v1/member-survey/results", headers=organiser_headers)
    assert r.status_code == 403


def test_results_requires_auth(client: Any) -> None:
    r = client.get("/api/v1/member-survey/results")
    assert r.status_code == 401


def test_unknown_barrier_rejected(client: Any) -> None:
    r = client.post(
        "/api/v1/member-survey/responses",
        json=_payload(q4_barriers=["no_time", "made_up_key"]),
    )
    assert r.status_code == 400
    assert "made_up_key" in r.text


def test_rating_out_of_range_rejected(client: Any) -> None:
    r = client.post(
        "/api/v1/member-survey/responses",
        json=_payload(q1_connected=6),
    )
    assert r.status_code == 422


def test_duplicate_barrier_keys_collapsed(client: Any, admin_headers: Any) -> None:
    r = client.post(
        "/api/v1/member-survey/responses",
        json=_payload(q4_barriers=["no_time", "no_time", "knows_no_one"]),
    )
    assert r.status_code == 201
    body = client.get(
        "/api/v1/member-survey/results", headers=admin_headers
    ).json()
    # The dedup happens in the router so a single submission counts
    # each barrier at most once.
    assert body["barrier_counts"]["no_time"] == 1
    assert body["barrier_counts"]["knows_no_one"] == 1
