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
        "name": name,
        "locale": locale,
    }
    if questions is not None:
        body["questions"] = questions
    r = client.post("/api/v1/forms", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# --- Create ----------------------------------------------------------


def test_create_form_minimal(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    assert form["name"] == "Demo form"
    assert form["locale"] == "nl"
    assert form["archived"] is False
    assert form["questions"] == []
    assert len(form["slug"]) == 8
    assert "id" in form


def test_create_form_with_initial_questions(client, organiser_headers):
    form = _create_form(
        client,
        organiser_headers,
        questions=[
            {"kind": "rating", "prompt": "How was it?", "required": True},
            {
                "kind": "single_choice",
                "prompt": "Pick one",
                "required": True,
                "options": ["A", "B", "C"],
            },
        ],
    )
    assert len(form["questions"]) == 2
    assert [q["ordinal"] for q in form["questions"]] == [1, 2]
    assert form["questions"][1]["options"] == ["A", "B", "C"]


def test_create_form_rejects_chapter_outside_user_membership(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    r = client.post(
        "/api/v1/forms",
        headers=organiser_headers,
        json={"chapter_id": other_chapter, "name": "Trespass", "locale": "nl"},
    )
    assert r.status_code == 403


def test_create_form_requires_authentication(client):
    r = client.post(
        "/api/v1/forms",
        json={"chapter_id": "x", "name": "Anonymous", "locale": "nl"},
    )
    assert r.status_code == 401


# --- List active + archived ------------------------------------------


def test_list_forms_returns_active_only(client, organiser_headers):
    live = _create_form(client, organiser_headers, name="Live")
    archived = _create_form(client, organiser_headers, name="Soon-archived")
    client.post(f"/api/v1/forms/{archived['id']}/archive", headers=organiser_headers)

    r = client.get("/api/v1/forms", headers=organiser_headers)
    assert r.status_code == 200
    ids = [f["id"] for f in r.json()]
    assert live["id"] in ids
    assert archived["id"] not in ids


def test_list_archived_returns_archived_only(client, organiser_headers):
    a = _create_form(client, organiser_headers, name="A")
    b = _create_form(client, organiser_headers, name="B")
    client.post(f"/api/v1/forms/{a['id']}/archive", headers=organiser_headers)

    r = client.get("/api/v1/forms/archived", headers=organiser_headers)
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

    r = client.get("/api/v1/forms", headers=organiser_headers)
    ids = [f["id"] for f in r.json()]
    assert mine["id"] in ids
    assert other["id"] not in ids


# --- Get single ------------------------------------------------------


def test_get_form_happy_path(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/forms/{form['id']}", headers=organiser_headers)
    assert r.status_code == 200
    assert r.json()["id"] == form["id"]


def test_get_form_other_chapter_404s(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    other = _create_form(client, admin_headers, name="Theirs", chapter_id=other_chapter)
    r = client.get(f"/api/v1/forms/{other['id']}", headers=organiser_headers)
    assert r.status_code == 404


# --- Update ----------------------------------------------------------


def test_update_form_renames(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    body = {**form, "name": "Renamed"}
    # ``FormUpdate`` only reads chapter_id/name/locale/questions —
    # extra fields ride along harmlessly.
    r = client.put(f"/api/v1/forms/{form['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_update_form_chapter_change_must_be_in_membership(client, admin_headers, organiser_headers):
    form = _create_form(client, organiser_headers)
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    body = {**form, "chapter_id": other_chapter}
    r = client.put(f"/api/v1/forms/{form['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 403


# --- Archive / restore / delete --------------------------------------


def test_archive_then_restore(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r1 = client.post(f"/api/v1/forms/{form['id']}/archive", headers=organiser_headers)
    assert r1.status_code == 200
    assert r1.json()["archived"] is True

    r2 = client.post(f"/api/v1/forms/{form['id']}/restore", headers=organiser_headers)
    assert r2.status_code == 200
    assert r2.json()["archived"] is False


def test_archive_already_archived_409s(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    client.post(f"/api/v1/forms/{form['id']}/archive", headers=organiser_headers)
    r = client.post(f"/api/v1/forms/{form['id']}/archive", headers=organiser_headers)
    assert r.status_code == 409


def test_restore_unarchived_409s(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.post(f"/api/v1/forms/{form['id']}/restore", headers=organiser_headers)
    assert r.status_code == 409


def test_delete_only_after_archive(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    # Live form delete refused.
    r = client.delete(f"/api/v1/forms/{form['id']}", headers=organiser_headers)
    assert r.status_code == 409

    client.post(f"/api/v1/forms/{form['id']}/archive", headers=organiser_headers)
    r = client.delete(f"/api/v1/forms/{form['id']}", headers=organiser_headers)
    assert r.status_code == 204

    # Vanished — get returns 404.
    r = client.get(f"/api/v1/forms/{form['id']}", headers=organiser_headers)
    assert r.status_code == 404


# --- Summary + submissions -------------------------------------------


def test_summary_empty_form(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["submission_count"] == 0
    assert body["questions"] == []


def test_submissions_empty_form(client, organiser_headers):
    form = _create_form(client, organiser_headers)
    r = client.get(f"/api/v1/forms/{form['id']}/submissions", headers=organiser_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_summary_other_chapter_404s(client, admin_headers, organiser_headers):
    r2 = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Utrecht"})
    other_chapter = r2.json()["id"]
    other = _create_form(client, admin_headers, name="Theirs", chapter_id=other_chapter)
    r = client.get(f"/api/v1/forms/{other['id']}/summary", headers=organiser_headers)
    assert r.status_code == 404


def test_image_delete_404_when_no_image(client, organiser_headers):
    """The image endpoints are wired + chapter-scoped. Deleting when
    there's no image 404s (no GitHub round-trip)."""
    form = _create_form(client, organiser_headers)
    r = client.delete(f"/api/v1/forms/{form['id']}/image", headers=organiser_headers)
    assert r.status_code == 404
