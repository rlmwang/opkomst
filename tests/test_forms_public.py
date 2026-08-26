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
        "name_nl": "Public form",
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
    assert body["name_nl"] == "Public form"
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


def test_submit_rating_out_of_range_400s(client, organiser_headers):
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
    # The 1-to-5 scale is checked per kind rather than on the schema:
    # ``answer_int`` is shared with ``number``, whose range belongs to
    # its own question. Rejected all the same, one layer in.
    assert r.status_code == 400


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


# --- number ---------------------------------------------------------
#
# The sixth kind. It shares ``answer_int`` with rating, which is the
# reason each of these exists: the 1-to-5 bound that belongs to rating
# moved out of the schema and into the per-kind validation, and a
# regression there is a form that silently refuses somebody's age.


def _number_form(client, headers, **question):
    q = {"kind": "number", "prompt": "Hoe oud ben je?", "required": True, **question}
    return _create(client, headers, questions=[q])


def test_number_accepts_a_value_outside_the_rating_scale(client, organiser_headers):
    """The bound that used to sit on the schema was ``1 <= n <= 5``.
    An age is the counter-example the kind exists for."""
    form = _number_form(client, organiser_headers)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 37}]},
    )
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        stored = db.query(FormResponse).filter(FormResponse.question_id == qid).one()
        assert stored.answer_int == 37


def test_number_accepts_zero(client, organiser_headers):
    """``0`` is an answer, not an empty box. A falsiness check anywhere
    on this path turns "none" into "unanswered"."""
    form = _number_form(client, organiser_headers, min_value=0)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": None, "answers": [{"question_id": qid, "answer_int": 0}]},
    )
    assert r.status_code == 201, r.text


def test_number_rejects_below_the_minimum(client, organiser_headers):
    form = _number_form(client, organiser_headers, min_value=18, max_value=120)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": None, "answers": [{"question_id": qid, "answer_int": 17}]},
    )
    assert r.status_code == 400


def test_number_rejects_above_the_maximum(client, organiser_headers):
    form = _number_form(client, organiser_headers, min_value=18, max_value=120)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    r = client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": None, "answers": [{"question_id": qid, "answer_int": 121}]},
    )
    assert r.status_code == 400


def test_number_bounds_and_step_reach_the_public_shape(client, organiser_headers):
    """The public page draws its own validation and its own hint line
    from these, so they have to arrive."""
    form = _number_form(client, organiser_headers, min_value=1, max_value=99, step=2)
    q = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]
    assert (q["min_value"], q["max_value"], q["step"]) == (1, 99, 2)


def test_a_form_rejects_a_minimum_above_the_maximum(client, organiser_headers):
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name_nl": "Impossible",
        "locale": "nl",
        "questions": [{"kind": "number", "prompt": "?", "min_value": 10, "max_value": 1}],
    }
    r = client.post("/api/v1/forms", headers=organiser_headers, json=body)
    assert r.status_code == 400


def test_bounds_are_dropped_when_the_kind_changes(client, organiser_headers):
    """Same normalisation every other kind gets: a question that stops
    being a number stops carrying a number's configuration."""
    form = _number_form(client, organiser_headers, min_value=1, max_value=99, step=2)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    r = client.put(
        f"/api/v1/forms/{form['id']}",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Public form",
            "locale": "nl",
            "questions": [
                {"id": qid, "kind": "short_text", "prompt": "Hoe oud ben je?", "min_value": 1, "unit": "jaar"}
            ],
        },
    )
    assert r.status_code == 200, r.text
    q = r.json()["questions"][0]
    assert (q["min_value"], q["max_value"], q["step"]) == (None, None, None)


def test_the_summary_reports_average_and_range(client, organiser_headers):
    form = _number_form(client, organiser_headers)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    for value in (10, 20, 30):
        client.post(
            f"/api/v1/forms/by-slug/{form['slug']}/submit",
            json={"display_name": None, "answers": [{"question_id": qid, "answer_int": value}]},
        )
    q = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers).json()["questions"][0]
    assert q["response_count"] == 3
    assert q["number_average"] == 20.0
    assert (q["number_min"], q["number_max"]) == (10, 30)


def test_the_csv_projection_carries_the_number(client, organiser_headers):
    form = _number_form(client, organiser_headers)
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 42}]},
    )
    rows = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers).json()
    assert rows[0]["answers"][qid] == 42


def test_a_number_question_can_demand_a_step(client, organiser_headers):
    """The step says which numbers count as an answer: 5 from a lowest
    of 0 accepts 0, 5, 10. A number off the step is refused the same way
    one out of range is."""
    form = _create(
        client,
        organiser_headers,
        questions=[
            {"kind": "number", "prompt": "Hoeveel?", "required": True, "min_value": 0, "max_value": 100, "step": 5}
        ],
    )
    qid = client.get(f"/api/v1/forms/by-slug/{form['slug']}").json()["questions"][0]["id"]

    def submit(value: int) -> int:
        return client.post(
            f"/api/v1/forms/by-slug/{form['slug']}/submit",
            json={"display_name": None, "answers": [{"question_id": qid, "answer_int": value}]},
        ).status_code

    assert submit(15) == 201
    assert submit(0) == 201
    assert submit(17) == 400


def test_a_step_no_number_can_land_on_is_refused(client, organiser_headers):
    """3 to 5 in steps of 7 accepts nothing at all, which is a question
    nobody can answer. Caught when the organiser saves."""
    body = {
        "chapter_id": _chapter_id(client, organiser_headers),
        "name_nl": "Onmogelijke stap",
        "locale": "nl",
        "questions": [{"kind": "number", "prompt": "Hoeveel?", "min_value": 3, "max_value": 5, "step": 7}],
    }
    assert client.post("/api/v1/forms", headers=organiser_headers, json=body).status_code == 400
