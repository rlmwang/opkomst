"""The three downloads an organiser can start.

A form, a datepoll and an event's feedback each offer a CSV, and all
three are written by the database and streamed out of one writer
(``services/csv_export``). What is proved here is what a spreadsheet
sees: English headers whatever language the page was read in, the
organiser's own words for their own questions, one column per question
in the order they are asked, and a row for every submission including
the ones that skipped a question.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from uuid_utils.compat import uuid7

from backend.database import SessionLocal
from backend.models import FeedbackToken, Occurrence, Registration, Signup
from tests._helpers.forms import option_ids


def _rows(response: Any) -> list[list[str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _form(client: Any, headers: Any, questions: list[dict[str, Any]]) -> dict[str, Any]:
    r = client.post(
        "/api/v1/form",
        headers=headers,
        json={
            "chapter_id": _chapter_id(client, headers),
            "name_nl": "Wat vind jij?",
            "locale": "nl",
            "questions": questions,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _submit(client: Any, form: dict[str, Any], name: str | None, answers: list[dict[str, Any]]) -> None:
    r = client.post(
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"display_name": name, "answers": answers},
    )
    assert r.status_code == 201, r.text


def test_the_form_download_is_one_column_per_question(client, organiser_headers):
    form = _form(
        client,
        organiser_headers,
        [
            {"kind": "rating", "prompt": "Hoe was het?", "required": True},
            {"kind": "short_text", "prompt": "Waarom?", "required": False},
        ],
    )
    rating, why = (q["id"] for q in form["questions"])
    _submit(
        client, form, "Sam", [{"question_id": rating, "answer_int": 4}, {"question_id": why, "answer_text": "Goed"}]
    )
    # Skipped the optional question: its cell is empty, not missing.
    _submit(client, form, None, [{"question_id": rating, "answer_int": 2}])

    rows = _rows(client.get(f"/api/v1/form/{form['id']}/submissions.csv", headers=organiser_headers))
    assert rows[0] == ["Name", "Submitted at", "Hoe was het?", "Waarom?"]
    assert rows[1][0] == "Sam"
    assert rows[1][2:] == ["4", "Goed"]
    assert rows[2][0] == "Anonymous"
    assert rows[2][2:] == ["2", ""]


def test_a_tick_is_exported_as_the_label_it_was_read_as(client, organiser_headers):
    form = _form(
        client,
        organiser_headers,
        [{"kind": "multiple_answer", "prompt": "Wat nam je mee?", "options": [{"label": "Soep"}, {"label": "Brood"}]}],
    )
    qid = form["questions"][0]["id"]
    _submit(
        client, form, "Sam", [{"question_id": qid, "answer_choices": option_ids(form["questions"][0], "Soep", "Brood")}]
    )

    rows = _rows(client.get(f"/api/v1/form/{form['id']}/submissions.csv", headers=organiser_headers))
    assert rows[1][2] == "Soep; Brood"


def test_the_kompas_download_carries_the_two_coordinates(client, organiser_headers):
    r = client.post(
        "/api/v1/compass",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Waar sta jij?",
            "locale": "nl",
            "axes": [
                {"axis": "x", "name": "Economie", "low_name": "Links", "high_name": "Rechts"},
                {"axis": "y", "name": "Cultuur", "low_name": "Open", "high_name": "Behoud"},
            ],
            "questions": [
                {"kind": "rating", "prompt": "Meer belasting", "pole": "x_high", "required": True},
                {"kind": "rating", "prompt": "Meer traditie", "pole": "y_high", "required": False},
            ],
        },
    )
    assert r.status_code == 201, r.text
    kompas = r.json()
    qid = kompas["questions"][0]["id"]
    r = client.post(
        f"/api/v1/compass/by-slug/{kompas['slug']}/submit",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 5}]},
    )
    assert r.status_code == 201, r.text

    rows = _rows(client.get(f"/api/v1/compass/{kompas['id']}/submissions.csv", headers=organiser_headers))
    assert rows[0] == ["Name", "Submitted at", "X", "Y", "Meer belasting", "Meer traditie"]
    assert rows[1][2:] == ["1.0", "0.0", "5", ""]


def test_the_datepoll_download_is_one_column_per_date(client, organiser_headers):
    r = client.post(
        "/api/v1/datepoll",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Wanneer kan iedereen?",
            "locale": "nl",
            "slots": [
                {"on_date": "2026-08-01"},
                {"on_date": "2026-08-02", "start_time": "19:00", "end_time": "21:00"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    poll = r.json()
    whole_day, evening = (s["id"] for s in poll["slots"])
    r = client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={
            "display_name": "Alex",
            "note": "liefst vroeg",
            # The evening is left unanswered: an empty cell, not a short row.
            "answers": [{"datepoll_slot_id": whole_day, "availability": "yes"}],
        },
    )
    assert r.status_code == 201, r.text
    r = client.post(
        f"/api/v1/datepoll/by-slug/{poll['slug']}/submit",
        json={"answers": [{"datepoll_slot_id": evening, "availability": "maybe"}]},
    )
    assert r.status_code == 201, r.text

    rows = _rows(client.get(f"/api/v1/datepoll/{poll['id']}/submissions.csv", headers=organiser_headers))
    assert rows[0] == ["Name", "Submitted at", "2026-08-01", "2026-08-02 19:00-21:00", "Note"]
    assert rows[1][0] == "Alex"
    assert rows[1][2:] == ["yes", "", "liefst vroeg"]
    assert rows[2][0] == "Anonymous"
    assert rows[2][2:] == ["", "maybe", ""]


def _feedback_token(event_id: str) -> str:
    """A signup and the token its feedback mail would carry. Seeded
    directly: what the download says is the subject here, not the day's
    worth of mail lifecycle that hands somebody the link."""
    db = SessionLocal()
    try:
        occ = db.query(Occurrence).filter(Occurrence.event_id == event_id).order_by(Occurrence.starts_at).first()
        assert occ is not None
        registration = Registration(event_id=event_id, display_name="Alice", party_size=1)
        db.add(registration)
        db.flush()
        db.add(Signup(registration_id=registration.id, occurrence_id=occ.id))
        raw = f"tok-{uuid7()}"
        db.add(FeedbackToken(token=raw, occurrence_id=occ.id, expires_at=datetime.now(UTC) + timedelta(days=30)))
        db.commit()
        return raw
    finally:
        db.close()


def test_the_feedback_download_names_its_columns_in_english(client, organiser_headers):
    r = client.post(
        "/api/v1/event",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Buurtvergadering",
            "location": "Adam",
            "starts_on": "2026-05-01",
            "start_time": "18:00:00",
            "end_time": "20:00:00",
            "source_options": [{"label": "Flyer"}],
            "feedback_enabled": True,
            "locale": "nl",
        },
    )
    assert r.status_code == 201, r.text
    event = r.json()
    token = _feedback_token(event["id"])
    # The two free-text answers are left out: empty cells, not a short row.
    r = client.post(
        f"/api/v1/feedback/{token}/submit",
        json={
            "answers": [
                {"question_key": "q1_overall", "answer_int": 5},
                {"question_key": "q2_recommend", "answer_int": 4},
                {"question_key": "q3_welcome", "answer_int": 3},
            ]
        },
    )
    assert r.status_code == 201, r.text

    rows = _rows(client.get(f"/api/v1/event/{event['id']}/feedback-submissions.csv", headers=organiser_headers))
    assert rows[0] == [
        "Submission",
        "Overall",
        "Would recommend",
        "Felt welcome",
        "What could be better",
        "Anything else",
    ]
    assert rows[1][1:] == ["5", "4", "3", "", ""]
