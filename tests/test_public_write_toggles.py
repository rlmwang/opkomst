"""Two switches the organiser owns, across every product.

* ``name_required`` — whether a public write is refused without a
  (pseudo)name. Off everywhere by default: a name real or not is what
  the contract offers, so an empty box is an answer. All six products
  carry it, so it is checked on all six here rather than six times over
  in six files.
* ``answers_editable`` — whether somebody may reopen their own link and
  change what they said. Every product that has an edit path: forms,
  kompassen, events and datepolls. A quiz has none, because seeing the
  score and then editing is the definition of cheating, and a roster's
  personal page is the product rather than a submission to reopen.

The refusal is the same shape everywhere: a 422 the visitor can act on,
raised in ``services/public_access``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


# --- one creator per product, each returning (public path, submit body) ---


def _event(client: Any, headers: Any, **over: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Demo",
        "location": "Adam",
        "starts_on": (date.today() + timedelta(days=14)).isoformat(),
        "start_time": "18:00:00",
        "end_time": "20:00:00",
        "locale": "nl",
        **over,
    }
    r = client.post("/api/v1/events", headers=headers, json=body)
    assert r.status_code == 201, r.text
    made = r.json()
    listed = client.get(f"/api/v1/events/{made['id']}/occurrences", headers=headers).json()
    made["_occurrence_slug"] = listed["occurrences"][0]["slug"]
    return made


def _form(client: Any, headers: Any, mode: str = "forms", **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Demo",
        "locale": "nl",
        "questions": [{"kind": "short_text", "prompt": "Waarom?", "required": False}],
        **over,
    }
    if mode == "compasses":
        body["axes"] = [
            {"axis": "x", "name": "Economie", "low_name": "Links", "high_name": "Rechts"},
            {"axis": "y", "name": "Cultuur", "low_name": "Open", "high_name": "Behoud"},
        ]
        # Both axes need a question, or nobody can move on one of them.
        body["questions"] = [
            {"kind": "rating", "prompt": "Stelling", "required": False, "pole": "x_high"},
            {"kind": "rating", "prompt": "Tweede", "required": False, "pole": "y_high"},
        ]
    if mode == "quizzes":
        # A quiz can only mark an answer it can compare, so its one
        # question is a rating rather than an open box.
        body["questions"] = [{"kind": "rating", "prompt": "Hoeveel?", "required": False, "points": 1, "correct_int": 4}]
    r = client.post(f"/api/v1/{mode}", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _datepoll(client: Any, headers: Any, **over: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Demo",
        "locale": "nl",
        "slots": [{"on_date": (date.today() + timedelta(days=14)).isoformat()}],
        **over,
    }
    r = client.post("/api/v1/datepolls", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _roster(client: Any, headers: Any, **over: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Demo",
        "starts_on": "2026-01-05",
        "chores": [{"name": "Bins", "cycle_slots": [2]}],
        **over,
    }
    r = client.post("/api/v1/chores", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _event_submit(client: Any, made: dict[str, Any], name: str | None) -> Any:
    # A sign-up is per occurrence, and an occurrence has its own public
    # slug; the organiser's occurrence list is where a test gets one.
    slug = made["_occurrence_slug"]
    return client.post(
        f"/api/v1/events/by-slug/{slug}/signups",
        json={"display_name": name, "party_size": 1, "all_upcoming": True},
    )


def _form_submit(client: Any, made: dict[str, Any], name: str | None, *, mode: str = "forms") -> Any:
    public = client.get(f"/api/v1/{mode}/by-slug/{made['slug']}").json()
    answers = [{"question_id": q["id"], "answer_int": 4} for q in public["questions"] if q["kind"] == "rating"]
    return client.post(
        f"/api/v1/{mode}/by-slug/{made['slug']}/submit",
        json={"display_name": name, "answers": answers},
    )


def _datepoll_submit(client: Any, made: dict[str, Any], name: str | None) -> Any:
    public = client.get(f"/api/v1/datepolls/by-slug/{made['slug']}").json()
    return client.post(
        f"/api/v1/datepolls/by-slug/{made['slug']}/submit",
        json={
            "display_name": name,
            "answers": [{"datepoll_slot_id": public["slots"][0]["id"], "availability": "yes"}],
        },
    )


def _roster_submit(client: Any, made: dict[str, Any], name: str | None) -> Any:
    return client.post(
        f"/api/v1/chores/by-slug/{made['slug']}/enroll",
        json={"display_name": name, "chore_ids": [made["chores"][0]["id"]]},
    )


# How a test makes one of each product and writes to it publicly, with
# the status a good write answers (the roster's enrol says 200: it hands
# back the personal-page token rather than creating a page of its own).
PRODUCTS = [
    (_event, _event_submit, 201),
    (lambda c, h, **o: _form(c, h, "forms", **o), _form_submit, 201),
    (lambda c, h, **o: _form(c, h, "quizzes", **o), lambda c, m, n: _form_submit(c, m, n, mode="quizzes"), 201),
    (lambda c, h, **o: _form(c, h, "compasses", **o), lambda c, m, n: _form_submit(c, m, n, mode="compasses"), 201),
    (_datepoll, _datepoll_submit, 201),
    (_roster, _roster_submit, 200),
]
IDS = ["event", "form", "quiz", "compass", "datepoll", "roster"]


# --- the name toggle -------------------------------------------------


@pytest.mark.parametrize(("make", "submit", "ok"), PRODUCTS, ids=IDS)
def test_a_nameless_answer_is_accepted_by_default(client, organiser_headers, make, submit, ok) -> None:
    made = make(client, organiser_headers)
    assert made["name_required"] is False
    r = submit(client, made, None)
    assert r.status_code == ok, r.text


@pytest.mark.parametrize(("make", "submit", "ok"), PRODUCTS, ids=IDS)
def test_a_nameless_answer_is_refused_when_the_organiser_asked_for_one(
    client, organiser_headers, make, submit, ok
) -> None:
    made = make(client, organiser_headers, name_required=True)
    assert made["name_required"] is True
    refused = submit(client, made, None)
    assert refused.status_code == 422, refused.text
    assert "name" in refused.json()["detail"].lower()
    # And a name, any name, gets through.
    assert submit(client, made, "Sam").status_code == ok


@pytest.mark.parametrize(("make", "submit", "ok"), PRODUCTS, ids=IDS)
def test_a_box_of_spaces_is_not_a_name(client, organiser_headers, make, submit, ok) -> None:
    """``DisplayName`` collapses whitespace to null before the check, so
    the toggle cannot be walked past with a spacebar."""
    del ok
    made = make(client, organiser_headers, name_required=True)
    assert submit(client, made, "   ").status_code == 422


def test_the_public_page_says_whether_it_wants_a_name(client, organiser_headers) -> None:
    """The mini-app reads this to decide whether the box is optional, so
    it has to be on the payload the page loads."""
    made = _form(client, organiser_headers, name_required=True)
    assert client.get(f"/api/v1/forms/by-slug/{made['slug']}").json()["name_required"] is True


# --- the edit toggle -------------------------------------------------


def test_a_form_answer_can_be_changed_by_default(client, organiser_headers) -> None:
    made = _form(client, organiser_headers)
    assert made["answers_editable"] is True
    token = _form_submit(client, made, "Sam").json()["edit_token"]
    r = client.put(f"/api/v1/forms/by-token/{token}", json={"display_name": "Kim", "answers": []})
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Kim"


def test_a_closed_form_refuses_the_change_and_still_opens_the_link(client, organiser_headers) -> None:
    made = _form(client, organiser_headers, answers_editable=False)
    token = _form_submit(client, made, "Sam").json()["edit_token"]

    r = client.put(f"/api/v1/forms/by-token/{token}", json={"display_name": "Kim", "answers": []})
    assert r.status_code == 409, r.text
    # Reading is not changing: the link still shows what was said.
    assert client.get(f"/api/v1/forms/by-token/{token}").json()["display_name"] == "Sam"


def test_a_closed_kompas_refuses_the_change(client, organiser_headers) -> None:
    made = _form(client, organiser_headers, "compasses", answers_editable=False)
    token = _form_submit(client, made, "Sam", mode="compasses").json()["edit_token"]
    r = client.put(f"/api/v1/compasses/by-token/{token}", json={"display_name": "Kim", "answers": []})
    assert r.status_code == 409, r.text


def test_a_closed_event_refuses_a_changed_booking(client, organiser_headers) -> None:
    made = _event(client, organiser_headers, answers_editable=False)
    token = _event_submit(client, made, "Sam").json()["edit_token"]
    r = client.put(f"/api/v1/events/by-token/{token}", json={"display_name": "Kim", "party_size": 2})
    assert r.status_code == 409, r.text


def test_a_closed_event_still_lets_somebody_out(client, organiser_headers) -> None:
    """Cancelling is not editing: an organiser who freezes the headcount
    is not holding people to it."""
    made = _event(client, organiser_headers, answers_editable=False)
    token = _event_submit(client, made, "Sam").json()["edit_token"]
    assert client.post(f"/api/v1/events/by-token/{token}/withdraw").status_code == 204


def test_a_closed_datepoll_refuses_the_change(client, organiser_headers) -> None:
    made = _datepoll(client, organiser_headers, answers_editable=False)
    token = _datepoll_submit(client, made, "Sam").json()["edit_token"]
    public = client.get(f"/api/v1/datepolls/by-slug/{made['slug']}").json()
    r = client.put(
        f"/api/v1/datepolls/by-token/{token}",
        json={
            "display_name": "Kim",
            "answers": [{"datepoll_slot_id": public["slots"][0]["id"], "availability": "no"}],
        },
    )
    assert r.status_code == 409, r.text


def test_withdrawing_is_never_closed(client, organiser_headers) -> None:
    """Changing your mind about the answers and taking them back are two
    different rights, and only the first is the organiser's to close."""
    made = _form(client, organiser_headers, answers_editable=False)
    token = _form_submit(client, made, "Sam").json()["edit_token"]
    assert client.post(f"/api/v1/forms/by-token/{token}/withdraw").status_code == 204


def test_the_toggles_survive_an_edit(client, organiser_headers) -> None:
    """Both flags are on the update payload, not just create. The quiz's
    ``reveal_answers`` sat in this same gap and was silently dropped on
    every save."""
    made = _form(client, organiser_headers, "quizzes")
    body = {
        "chapter_id": made["chapter_id"],
        "name_nl": "Demo",
        "locale": "nl",
        "questions": [{"kind": "rating", "prompt": "Hoeveel?", "required": False, "points": 1, "correct_int": 4}],
        "reveal_answers": False,
        "answers_editable": False,
        "name_required": True,
    }
    r = client.put(f"/api/v1/quizzes/{made['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200, r.text
    assert (r.json()["reveal_answers"], r.json()["answers_editable"], r.json()["name_required"]) == (
        False,
        False,
        True,
    )
