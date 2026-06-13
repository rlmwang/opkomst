"""Coverage for the public-by-slug forms surface: GET the form
shape, POST submissions with per-kind validation, archived 410s.

The kind enum is the load-bearing contract — every kind has both
a happy-path and a rejection test here so the public submit
handler can't silently start accepting bad shapes.
"""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import FormResponse


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, questions: list[dict[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chapter_id": _chapter_id(client, headers),
        "name": "Public form",
        "locale": "nl",
        "questions": questions,
    }
    r = client.post("/api/v1/forms", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- GET /by-slug/{slug} --------------------------------------------


def test_public_get_returns_questions(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "How was it?", "required": True},
        ],
    )
    r = client.get(f"/api/v1/forms/by-slug/{form['slug']}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Public form"
    assert body["locale"] == "nl"
    assert len(body["questions"]) == 1


def test_public_get_unknown_slug_410s(client):
    r = client.get("/api/v1/forms/by-slug/no-such")
    assert r.status_code == 410


def test_public_get_archived_form_410s(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "X", "required": True},
        ],
    )
    client.post(f"/api/v1/forms/{form['id']}/archive", headers=organiser_headers)
    r = client.get(f"/api/v1/forms/by-slug/{form['slug']}")
    assert r.status_code == 410


# --- rating ---------------------------------------------------------


def test_submit_rating_happy_path(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True, "low_label": "Bad", "high_label": "Good"},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 4}]},
    )
    assert r.status_code == 201
    assert "submission_id" in r.json()


def test_submit_rating_out_of_range_422s(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 9}]},
    )
    # Pydantic schema bounds (ge=1, le=5) reject this at the
    # validation layer before the kind code sees it.
    assert r.status_code == 422


def test_submit_required_skipped_400s(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    r = client.post(f"/api/v1/forms/by-slug/{form['slug']}/submit", json={"answers": []})
    assert r.status_code == 400


# --- pseudonym -------------------------------------------------------


def test_submit_stores_pseudonym(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={
            "display_name": "Sam",
            "answers": [{"question_id": qid, "answer_int": 4}],
        },
    )
    subs = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert len(subs) == 1
    assert subs[0]["display_name"] == "Sam"
    assert subs[0]["answers"][qid] == 4


def test_submit_anonymous_pseudonym_is_null(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    # whitespace-only collapses to anonymous (shared DisplayName primitive)
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={
            "display_name": "  ",
            "answers": [{"question_id": qid, "answer_int": 4}],
        },
    )
    subs = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert subs[0]["display_name"] is None


# --- text / short_text ----------------------------------------------


def test_submit_text_happy_path(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "text", "prompt": "Comments", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_text": "Nice work"}]},
    )
    assert r.status_code == 201
    db = SessionLocal()
    try:
        row = db.query(FormResponse).filter(FormResponse.form_id == form["id"]).one()
        assert row.answer_text == "Nice work"
        assert row.answer_int is None
        assert row.answer_choices is None
    finally:
        db.close()


def test_submit_short_text_whitespace_only_treated_as_skipped(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "short_text", "prompt": "Name", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_text": "   "}]},
    )
    # Whitespace-only collapses to "skipped"; required check fails.
    assert r.status_code == 400


# --- single_choice --------------------------------------------------


def test_submit_single_choice_happy_path(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "single_choice", "prompt": "Pick", "required": True, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": ["B"]}]},
    )
    assert r.status_code == 201
    db = SessionLocal()
    try:
        row = db.query(FormResponse).filter(FormResponse.form_id == form["id"]).one()
        assert row.answer_choices == ["B"]
    finally:
        db.close()


def test_submit_single_choice_rejects_value_not_in_options(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "single_choice", "prompt": "Pick", "required": True, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": ["Z"]}]},
    )
    assert r.status_code == 400


def test_submit_single_choice_rejects_more_than_one(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "single_choice", "prompt": "Pick", "required": True, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": ["A", "B"]}]},
    )
    assert r.status_code == 400


# --- multi_choice ---------------------------------------------------


def test_submit_multi_choice_dedupes(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "multi_choice", "prompt": "Pick", "required": False, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": ["A", "A", "B"]}]},
    )
    assert r.status_code == 201
    db = SessionLocal()
    try:
        row = db.query(FormResponse).filter(FormResponse.form_id == form["id"]).one()
        assert row.answer_choices == ["A", "B"]
    finally:
        db.close()


def test_submit_multi_choice_rejects_unknown_option(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "multi_choice", "prompt": "Pick", "required": False, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": ["A", "Z"]}]},
    )
    assert r.status_code == 400


def test_submit_optional_multi_choice_empty_is_skipped(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "multi_choice", "prompt": "Pick", "required": False, "options": ["A", "B"]},
        ],
    )
    qid = form["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_choices": []}]},
    )
    assert r.status_code == 201
    db = SessionLocal()
    try:
        assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).count() == 0
    finally:
        db.close()


# --- Submissions go into the summary + CSV ---------------------------


def test_submit_then_summary_reflects_response(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 5}]},
    )

    r = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers)
    body = r.json()
    assert body["submission_count"] == 1
    assert body["questions"][0]["rating_distribution"] == [0, 0, 0, 0, 1]


def test_submit_rate_limit_fires(client, organiser_headers):
    """``PUBLIC_SUBMIT`` limit on the public submit endpoint
    (20/hour). The 21st submission from the same IP within the
    window must 429.

    The test relies on ``client`` fixture's ``limiter.reset()``
    on setup — the limiter is in-process and a clean budget
    starts at zero. Each successful submit consumes one slot
    against the same form/IP pair."""
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "S", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    body = {"answers": [{"question_id": qid, "answer_int": 5}]}

    # 20 should sail through; 21st must 429. ``test_login_link_rate_limit``
    # uses the same shape against a 5/hour route.
    for _ in range(20):
        r = client.post(f"/api/v1/forms/by-slug/{form['slug']}/submit", json=body)
        assert r.status_code == 201, r.text
    r = client.post(f"/api/v1/forms/by-slug/{form['slug']}/submit", json=body)
    assert r.status_code == 429


def test_submit_then_csv_source_includes_row(client, organiser_headers):
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "Score", "required": True},
        ],
    )
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"answers": [{"question_id": qid, "answer_int": 5}]},
    )
    r = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers)
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["answers"][qid] == 5
