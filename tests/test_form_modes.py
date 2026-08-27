"""The forms table holds two products, and nothing may read it without
saying which one it means.

``docs/design-quizzes.md`` part 1 chose one set of tables for surveys
and quizzes over two parallel sets, and named the price: every read of
``Form`` must filter on ``mode``, and a read that forgets is invisible
until an organiser finds a quiz in their questionnaire list. These tests
are that price being paid.

The grep is the same mechanism ``test_privacy.py`` uses to keep
``encryption.decrypt`` inside the mail worker: ugly, and the only thing
that actually holds a boundary a convention cannot.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any

from backend.database import SessionLocal
from backend.models import Form
from backend.services import forms as forms_svc

_BACKEND = pathlib.Path(__file__).resolve().parent.parent / "backend"
# The one module allowed to build a query against this table.
_OWNER = _BACKEND / "services" / "forms.py"


def test_only_the_service_queries_the_forms_table() -> None:
    """``services/forms.query(db, mode)`` is the single door. A
    ``db.query(Form)`` anywhere else is a read with no mode predicate,
    which is the whole failure this design has to prevent."""
    offenders = []
    for path in _BACKEND.rglob("*.py"):
        if path == _OWNER or "alembic" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"\.query\(\s*Form\s*\)", line):
                offenders.append(f"{path.relative_to(_BACKEND.parent)}:{lineno}: {line.strip()}")
    assert not offenders, "read the forms table through services.forms.query(db, mode):\n" + "\n".join(offenders)


def test_the_service_query_filters_on_the_mode_it_is_given() -> None:
    """The door itself, from the other side: the predicate is in the
    SQL rather than in the docstring."""
    with SessionLocal() as db:
        assert "mode" in str(forms_svc.query(db, "survey"))


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _make_form(client: Any, headers: Any, name: str) -> dict[str, Any]:
    r = client.post(
        "/api/v1/forms",
        headers=headers,
        json={
            "chapter_id": _chapter_id(client, headers),
            "name_nl": name,
            "locale": "nl",
            # Every product needs at least one question to be savable.
            "questions": [{"kind": "short_text", "prompt": "Waarom?", "required": False}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_a_form_created_through_the_api_is_a_survey(client, organiser_headers) -> None:
    """The mode is written, not left to the column default, so the row
    says what it is even when it was made by a path that predates the
    other product."""
    form = _make_form(client, organiser_headers, "Een vragenlijst")
    with SessionLocal() as db:
        assert db.get(Form, form["id"]).mode == "survey"


def test_a_quiz_row_stays_out_of_the_forms_list(client, organiser_headers) -> None:
    """The failure this whole seam exists for, written as a test before
    there is a quiz surface to produce it."""
    form = _make_form(client, organiser_headers, "Wordt een quiz")
    with SessionLocal() as db:
        row = db.get(Form, form["id"])
        row.mode = "quiz"
        db.commit()
    listed = client.get("/api/v1/forms", headers=organiser_headers).json()
    assert form["id"] not in [f["id"] for f in listed]


def test_a_quiz_is_not_reachable_through_a_form_url(client, organiser_headers) -> None:
    """Public by-slug, the organiser's single fetch, and the archive
    list: each one is its own door and each one is closed."""
    form = _make_form(client, organiser_headers, "Ook een quiz")
    with SessionLocal() as db:
        row = db.get(Form, form["id"])
        row.mode = "quiz"
        db.commit()
    assert client.get(f"/api/v1/forms/by-slug/{form['slug']}").status_code == 410
    assert client.get(f"/api/v1/forms/{form['id']}", headers=organiser_headers).status_code == 404
    archived = client.get("/api/v1/forms/archived", headers=organiser_headers).json()
    assert form["id"] not in [f["id"] for f in archived]


def test_the_public_html_route_does_not_serve_a_quiz_as_a_form(client, organiser_headers) -> None:
    """``/f/{slug}`` is the survey mini-app. A quiz slug there is the
    same "no longer available" a stale link gets, not somebody else's
    page rendered in the wrong shell."""
    form = _make_form(client, organiser_headers, "Quiz via de HTML-route")
    with SessionLocal() as db:
        row = db.get(Form, form["id"])
        row.mode = "quiz"
        db.commit()
    response = client.get(f"/f/{form['slug']}")
    assert response.status_code == 404
    assert "Quiz via de HTML-route" not in response.text
