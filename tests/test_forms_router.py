"""Coverage for the organiser-side forms router.

Mirrors the events-router test structure: create, list active,
list archived, single fetch, update, archive, restore, delete-
only-when-archived, chapter scoping (an organiser can only see
forms in their own chapter), and the summary / submissions
endpoints.

The diff-apply logic on the question payload has its own file
(``test_form_questions.py``); per-kind validation on the public
submit endpoint lives in ``test_forms_public.py``.
"""

from __future__ import annotations

from typing import Any


def _chapter_id(client: Any, headers: Any) -> str:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return me["chapters"][0]["id"]


def _create_form(
    client: Any,
    headers: Any,
    *,
    name: str = "Demo form",
    locale: str = "nl",
    questions: list[dict[str, Any]] | None = None,
    chapter_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chapter_id": chapter_id or _chapter_id(client, headers),
        "name_nl": name,
        "locale": locale,
        # A form with no questions is refused, so the default here is
        # one throwaway question the caller can replace.
        "questions": [{"kind": "short_text", "prompt": "Waarom?", "required": False}],
    }
    if questions is not None:
        body["questions"] = questions
    r = client.post("/api/v1/form", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- Create ----------------------------------------------------------


def test_create_form_minimal(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    assert form["name_nl"] == "Demo form"
    assert form["locale"] == "nl"
    assert form["archived"] is False
    assert len(form["questions"]) == 1
    assert len(form["slug"]) == 8
    assert "id" in form


def test_a_form_with_nothing_to_answer_is_refused(client, organiser_headers):
    """There is no empty draft: a questionnaire with no questions is a
    public page whose only button does nothing."""
    r = client.post(
        "/api/v1/form",
        headers=organiser_headers,
        json={"chapter_id": _chapter_id(client, organiser_headers), "name_nl": "Leeg", "locale": "nl", "questions": []},
    )
    assert r.status_code == 400, r.text
    assert "at least one question" in r.json()["detail"]


def test_create_form_with_initial_questions(client, organiser_headers):
    form = _create_form(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "How was it?", "required": True},
            {
                "kind": "multiple_choice",
                "prompt": "Pick one",
                "required": True,
                "options": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
            },
        ],
    )
    assert len(form["questions"]) == 2
    assert [q["ordinal"] for q in form["questions"]] == [1, 2]
    assert [o["label"] for o in form["questions"][1]["options"]] == ["A", "B", "C"]


def test_create_form_rejects_chapter_outside_user_membership(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    r = client.post(
        "/api/v1/form",
        headers=organiser_headers,
        json={"chapter_id": other_chapter, "name_nl": "Trespass", "locale": "nl"},
    )
    assert r.status_code == 403


def test_create_form_requires_authentication(client):
    r = client.post(
        "/api/v1/form",
        json={"chapter_id": "x", "name_nl": "Anonymous", "locale": "nl"},
    )
    assert r.status_code == 401


# --- List active + archived ------------------------------------------


def test_list_forms_returns_active_only(client, organiser_headers):
    live = _create_form(client, organiser_headers, name="Live")
    archived = _create_form(client, organiser_headers, name="Soon-archived")
    client.post(f"/api/v1/form/{archived['id']}/archive", headers=organiser_headers)

    r = client.get("/api/v1/form", headers=organiser_headers)
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()]
    assert live["id"] in ids
    assert archived["id"] not in ids


def test_list_archived_returns_archived_only(client, organiser_headers):
    a = _create_form(client, organiser_headers, name="A")
    b = _create_form(client, organiser_headers, name="B")
    client.post(f"/api/v1/form/{a['id']}/archive", headers=organiser_headers)

    r = client.get("/api/v1/form/archived", headers=organiser_headers)
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()]
    assert a["id"] in ids
    assert b["id"] not in ids


def test_list_other_chapter_excluded(client, admin_headers, organiser_headers):
    """A form in a chapter the organiser doesn't belong to must
    not appear in their list."""
    mine = _create_form(client, organiser_headers, name="Mine")
    # New chapter + admin-only form there.
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    other = _create_form(client, admin_headers, name="Theirs", chapter_id=other_chapter)

    r = client.get("/api/v1/form", headers=organiser_headers)
    ids = [f["id"] for f in r.json()]
    assert mine["id"] in ids
    assert other["id"] not in ids


# --- Get single ------------------------------------------------------


def test_get_form_happy_path(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/form/{form['id']}", headers=organiser_headers)
    assert r.status_code == 200
    assert r.json()["id"] == form["id"]


def test_get_form_other_chapter_404s(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    other = _create_form(client, admin_headers, name="Theirs", chapter_id=other_chapter)
    r = client.get(f"/api/v1/form/{other['id']}", headers=organiser_headers)
    assert r.status_code == 404


# --- Update ----------------------------------------------------------


def test_update_form_renames(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    body = {**form, "name_nl": "Renamed"}
    # ``FormUpdate`` only reads chapter_id/name/locale/questions —
    # extra fields ride along harmlessly.
    r = client.put(f"/api/v1/form/{form['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200
    assert r.json()["name_nl"] == "Renamed"


def test_update_form_chapter_change_must_be_in_membership(client, admin_headers, organiser_headers):
    form = _create_form(client, organiser_headers)
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    body = {**form, "chapter_id": other_chapter}
    r = client.put(f"/api/v1/form/{form['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 403


# --- Archive / restore / delete --------------------------------------


def test_archive_then_restore(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r1 = client.post(f"/api/v1/form/{form['id']}/archive", headers=organiser_headers)
    assert r1.status_code == 200
    assert r1.json()["archived"] is True

    r2 = client.post(f"/api/v1/form/{form['id']}/restore", headers=organiser_headers)
    assert r2.status_code == 200
    assert r2.json()["archived"] is False


def test_archiving_twice_is_a_404(client, organiser_headers):
    """The first archive moves the form out of ``forms``; the second has
    nothing live to find."""
    form = _create_form(client, organiser_headers)
    client.post(f"/api/v1/form/{form['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/form/{form['id']}/archive", headers=organiser_headers)
    assert r.status_code == 404


def test_restoring_something_live_is_a_404(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.post(f"/api/v1/form/{form['id']}/restore", headers=organiser_headers)
    assert r.status_code == 404


def test_delete_only_after_archive(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    # A live form is not in the archive, so the delete route cannot find
    # it: archiving first is still the only way to delete.
    r = client.delete(f"/api/v1/form/{form['id']}", headers=organiser_headers)
    assert r.status_code == 404

    client.post(f"/api/v1/form/{form['id']}/archive", headers=organiser_headers)
    r = client.delete(f"/api/v1/form/{form['id']}", headers=organiser_headers)
    assert r.status_code == 204

    # Vanished — get returns 404.
    r = client.get(f"/api/v1/form/{form['id']}", headers=organiser_headers)
    assert r.status_code == 404


# --- Summary + submissions -------------------------------------------


def test_summary_empty_form(client, organiser_headers):
    """Nobody has answered yet: a question with no responses is still on
    the summary, with nothing counted against it."""
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/form/{form['id']}/summary", headers=organiser_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["submission_count"] == 0
    assert [q["response_count"] for q in body["questions"]] == [0]


def test_submissions_empty_form(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/form/{form['id']}/submissions", headers=organiser_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_summary_other_chapter_404s(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    other = _create_form(client, admin_headers, name="Theirs", chapter_id=other_chapter)
    r = client.get(f"/api/v1/form/{other['id']}/summary", headers=organiser_headers)
    assert r.status_code == 404


def test_image_delete_404_when_no_image(client, organiser_headers):
    """The image endpoints are wired + chapter-scoped. Deleting when
    there's no image 404s (no GitHub round-trip)."""
    form = _create_form(client, organiser_headers)
    r = client.delete(f"/api/v1/form/{form['id']}/image", headers=organiser_headers)
    assert r.status_code == 404
