"""Coverage for the question diff-apply on form create + update.

Add / edit-in-place / delete-and-cascade / reorder / kind-aware
field normalisation. The diff-apply logic lives in
``services/forms.apply_questions``; the router test file
(``test_forms_router.py``) covers the surrounding CRUD.
"""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import FormQuestion, FormResponse


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create(client: Any, headers: Any, questions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chapter_id": _chapter_id(client, headers),
        "name": "Test form",
        "locale": "nl",
    }
    if questions is not None:
        body["questions"] = questions
    r = client.post("/api/v1/forms", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _put(client: Any, headers: Any, form: dict[str, Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
    body = {
        "chapter_id": form["chapter_id"],
        "name": form["name"],
        "locale": form["locale"],
        "questions": questions,
    }
    r = client.put(f"/api/v1/forms/{form['id']}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# --- Add / edit / delete --------------------------------------------


def test_can_add_a_question_on_update(client, organiser_headers):
    form = _create(client, organiser_headers)
    out = _put(client, organiser_headers, form, [
        {"kind": "rating", "prompt": "How was it?", "required": True},
    ])
    assert len(out["questions"]) == 1
    assert out["questions"][0]["prompt"] == "How was it?"


def test_edit_in_place_preserves_id(client, organiser_headers):
    form = _create(client, organiser_headers, questions=[
        {"kind": "rating", "prompt": "Old", "required": True},
    ])
    qid = form["questions"][0]["id"]
    out = _put(client, organiser_headers, form, [
        {"id": qid, "kind": "rating", "prompt": "New", "required": True},
    ])
    assert out["questions"][0]["id"] == qid
    assert out["questions"][0]["prompt"] == "New"


def test_reordering_by_input_order(client, organiser_headers):
    form = _create(client, organiser_headers, questions=[
        {"kind": "rating", "prompt": "Q1", "required": True},
        {"kind": "rating", "prompt": "Q2", "required": True},
        {"kind": "rating", "prompt": "Q3", "required": True},
    ])
    ids = [q["id"] for q in form["questions"]]
    out = _put(client, organiser_headers, form, [
        {"id": ids[2], "kind": "rating", "prompt": "Q3", "required": True},
        {"id": ids[0], "kind": "rating", "prompt": "Q1", "required": True},
        {"id": ids[1], "kind": "rating", "prompt": "Q2", "required": True},
    ])
    assert [q["id"] for q in out["questions"]] == [ids[2], ids[0], ids[1]]
    assert [q["ordinal"] for q in out["questions"]] == [1, 2, 3]


def test_removed_question_cascades_to_responses(client, organiser_headers):
    form = _create(client, organiser_headers, questions=[
        {"kind": "rating", "prompt": "Q1", "required": True},
        {"kind": "rating", "prompt": "Q2", "required": True},
    ])
    q1_id = form["questions"][0]["id"]

    # Plant a response against q1.
    db = SessionLocal()
    try:
        db.add(FormResponse(
            form_id=form["id"],
            question_id=q1_id,
            submission_id="sub-1",
            answer_int=5,
        ))
        db.commit()
        assert db.query(FormResponse).filter(FormResponse.question_id == q1_id).count() == 1
    finally:
        db.close()

    # Drop q1.
    _put(client, organiser_headers, form, [form["questions"][1]])

    db = SessionLocal()
    try:
        assert db.query(FormQuestion).filter(FormQuestion.id == q1_id).count() == 0
        assert db.query(FormResponse).filter(FormResponse.question_id == q1_id).count() == 0
    finally:
        db.close()


# --- Validation ------------------------------------------------------


def test_choice_with_one_option_400s(client, organiser_headers):
    r = client.post("/api/v1/forms", headers=organiser_headers, json={
        "chapter_id": _chapter_id(client, organiser_headers),
        "name": "F",
        "locale": "nl",
        "questions": [{
            "kind": "single_choice",
            "prompt": "Pick",
            "required": True,
            "options": ["only-one"],
        }],
    })
    assert r.status_code == 400
    assert "two options" in r.json()["detail"]


def test_choice_with_duplicate_options_400s(client, organiser_headers):
    r = client.post("/api/v1/forms", headers=organiser_headers, json={
        "chapter_id": _chapter_id(client, organiser_headers),
        "name": "F",
        "locale": "nl",
        "questions": [{
            "kind": "multi_choice",
            "prompt": "Pick many",
            "required": False,
            "options": ["a", "a", "b"],
        }],
    })
    assert r.status_code == 400
    assert "unique" in r.json()["detail"]


def test_kind_normalisation_strips_options_for_non_choice(client, organiser_headers):
    """An organiser submitting ``options`` on a text question (e.g.
    because the frontend didn't clean its state when switching
    kinds) shouldn't see them stored. The server tidies up."""
    form = _create(client, organiser_headers, questions=[
        {
            "kind": "text",
            "prompt": "Free form",
            "required": False,
            "options": ["leftover-a", "leftover-b"],
            "low_label": "ignored",
            "high_label": "also ignored",
        },
    ])
    q = form["questions"][0]
    assert q["options"] == []
    assert q["low_label"] is None
    assert q["high_label"] is None
