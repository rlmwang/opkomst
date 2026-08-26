"""A quiz is a questionnaire with a right answer.

What is tested here is only the part that differs (``docs/design-
quizzes.md``): the key, the grading, the score that outlives an edit,
and the two doors that are deliberately shut. Everything else about a
quiz is a form, and is covered by the forms suites through the same
code.

The grading rules, in one place, because each of them is a decision:

* a wrong answer and an unanswered optional question are both worth
  nothing;
* multi-choice is exact-set, no partial credit;
* short text ignores case and spacing, because a phone keyboard should
  not cost a point;
* a number may carry a tolerance;
* ``text`` cannot be graded and is always worth zero.
"""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import Form, FormResponse, FormSubmission


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _quiz(client: Any, headers: Any, questions: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    body = {
        "chapter_id": _chapter_id(client, headers),
        "name_nl": "Pubquiz",
        "locale": "nl",
        "questions": questions,
        **extra,
    }
    r = client.post("/api/v1/quizzes", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _take(client: Any, quiz: dict[str, Any], answers: list[dict[str, Any]], name: str | None = "Sam") -> Any:
    return client.post(
        f"/api/v1/quizzes/by-slug/{quiz['slug']}/submit",
        json={"display_name": name, "answers": answers},
    )


# --- the key and the score -------------------------------------------


def test_a_right_answer_scores_and_a_wrong_one_does_not(client, organiser_headers) -> None:
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {"kind": "short_text", "prompt": "Hoofdstad?", "points": 3, "correct_text": "Amsterdam"},
            {"kind": "number", "prompt": "Hoeveel provincies?", "points": 2, "correct_int": 12},
        ],
    )
    qs = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"]
    r = _take(
        client,
        quiz,
        [
            {"question_id": qs[0]["id"], "answer_text": "amsterdam"},
            {"question_id": qs[1]["id"], "answer_int": 11},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["score"], body["max_score"]) == (3, 5)
    by_q = {a["question_id"]: a for a in body["answers"]}
    assert by_q[qs[0]["id"]]["correct"] is True
    assert by_q[qs[1]["id"]]["correct"] is False


def test_short_text_ignores_case_and_spacing(client, organiser_headers) -> None:
    """A phone keyboard capitalises; a person types two spaces. Neither
    is a different answer."""
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "short_text", "prompt": "Wie?", "points": 1, "correct_text": "Den Haag"}],
    )
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    assert _take(client, quiz, [{"question_id": qid, "answer_text": "  den  haag "}]).json()["score"] == 1


def test_multi_choice_is_all_or_nothing(client, organiser_headers) -> None:
    """No partial credit: a rule for wrong extras is arguable, and
    exact-set is the one nobody has to explain."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "multi_choice",
                "prompt": "Welke twee?",
                "points": 4,
                "options": ["A", "B", "C"],
                "correct_choices": ["A", "B"],
            }
        ],
    )
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    assert _take(client, quiz, [{"question_id": qid, "answer_choices": ["A", "B"]}]).json()["score"] == 4
    assert _take(client, quiz, [{"question_id": qid, "answer_choices": ["A"]}]).json()["score"] == 0
    assert _take(client, quiz, [{"question_id": qid, "answer_choices": ["A", "B", "C"]}]).json()["score"] == 0


def test_a_number_may_be_close_enough(client, organiser_headers) -> None:
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoe hoog?", "points": 2, "correct_int": 100, "tolerance": 5}],
    )
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    assert _take(client, quiz, [{"question_id": qid, "answer_int": 96}]).json()["score"] == 2
    assert _take(client, quiz, [{"question_id": qid, "answer_int": 94}]).json()["score"] == 0


def test_an_open_question_is_asked_and_never_scored(client, organiser_headers) -> None:
    """No rule grades a paragraph. It is allowed, worth zero, and does
    not count toward the total."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {"kind": "text", "prompt": "Waarom?", "points": 5, "required": False},
            {"kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 7},
        ],
    )
    saved = client.get(f"/api/v1/quizzes/{quiz['id']}", headers=organiser_headers).json()
    assert saved["questions"][0]["points"] == 0
    qs = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"]
    body = _take(client, quiz, [{"question_id": qs[1]["id"], "answer_int": 7}]).json()
    assert (body["score"], body["max_score"]) == (1, 1)
    assert [a["question_id"] for a in body["answers"]] == [qs[1]["id"]]


def test_an_unanswered_optional_question_is_worth_nothing(client, organiser_headers) -> None:
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoeveel?", "points": 3, "correct_int": 7, "required": False}],
    )
    body = _take(client, quiz, []).json()
    assert (body["score"], body["max_score"]) == (0, 3)


# --- the key never leaves early ---------------------------------------


def test_the_public_shape_carries_no_answer_key(client, organiser_headers) -> None:
    """The one test standing between a quiz and being solved by
    view-source.

    Field-set equality rather than "the key is not in the body": a
    substring check passes by accident (a uuid contains "42") and, more
    importantly, it cannot fail for a field nobody has thought of yet.
    ``PublicQuestionOut`` lists its fields for the same reason, and this
    is the assertion that makes that list load-bearing."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Welke?",
                "points": 1,
                "options": ["Rotterdam", "Zwolle"],
                "correct_choices": ["Zwolle"],
            },
            {"kind": "short_text", "prompt": "Wie?", "points": 1, "correct_text": "Domela"},
            {"kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 42, "tolerance": 2},
        ],
    )
    response = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}")
    allowed = {
        "id",
        "ordinal",
        "kind",
        "prompt",
        "required",
        "options",
        # What it is worth is not a secret, and on a quiz it is worth
        # knowing before you answer.
        "points",
        "low_label",
        "high_label",
        "min_value",
        "max_value",
        "unit",
    }
    for q in response.json()["questions"]:
        assert set(q) == allowed, sorted(set(q) - allowed)
    # The one key value distinctive enough to grep for safely.
    assert "Domela" not in response.text
    # And what it may carry.
    assert response.json()["questions"][0]["options"] == ["Rotterdam", "Zwolle"]


def test_the_result_reveals_the_key_only_when_the_quiz_says_so(client, organiser_headers) -> None:
    """An organiser running the same quiz twice in one evening turns
    the reveal off; the score still arrives."""
    questions = [{"kind": "short_text", "prompt": "Wie?", "points": 1, "correct_text": "Domela"}]
    open_quiz = _quiz(client, organiser_headers, questions)
    closed_quiz = _quiz(client, organiser_headers, questions, reveal_answers=False)

    qid = client.get(f"/api/v1/quizzes/by-slug/{open_quiz['slug']}").json()["questions"][0]["id"]
    revealed = _take(client, open_quiz, [{"question_id": qid, "answer_text": "iemand"}]).json()
    assert revealed["reveal_answers"] is True
    assert revealed["answers"][0]["correct_text"] == "Domela"

    qid = client.get(f"/api/v1/quizzes/by-slug/{closed_quiz['slug']}").json()["questions"][0]["id"]
    hidden = _take(client, closed_quiz, [{"question_id": qid, "answer_text": "iemand"}]).json()
    assert hidden["reveal_answers"] is False
    assert hidden["answers"][0]["correct_text"] is None
    assert hidden["answers"][0]["correct"] is False


# --- the score outlives the quiz --------------------------------------


def test_a_score_survives_the_quiz_being_edited(client, organiser_headers) -> None:
    """The reason score and max_score are stored rather than computed:
    an organiser adds a question afterwards and an old result still
    says what it said on the day."""
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 7}],
    )
    qs = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"]
    result = _take(client, quiz, [{"question_id": qs[0]["id"], "answer_int": 7}]).json()
    assert (result["score"], result["max_score"]) == (1, 1)

    saved = client.get(f"/api/v1/quizzes/{quiz['id']}", headers=organiser_headers).json()
    client.put(
        f"/api/v1/quizzes/{quiz['id']}",
        headers=organiser_headers,
        json={
            "chapter_id": saved["chapter_id"],
            "name_nl": "Pubquiz",
            "locale": "nl",
            "questions": [
                {"id": qs[0]["id"], "kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 7},
                {"kind": "number", "prompt": "En nu?", "points": 9, "correct_int": 3},
            ],
        },
    )
    again = client.get(f"/api/v1/quizzes/by-token/{result['edit_token']}").json()
    assert (again["score"], again["max_score"]) == (1, 1)


# --- the doors that are shut ------------------------------------------


def test_a_taken_quiz_cannot_be_answered_again(client, organiser_headers) -> None:
    """Editing an answer after seeing the score is a second attempt.
    The token opens the result and nothing else."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    token = _take(client, quiz, [{"question_id": qid, "answer_int": 1}]).json()["edit_token"]
    r = client.put(
        f"/api/v1/quizzes/by-token/{token}",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 7}]},
    )
    assert r.status_code == 405


def test_a_taker_can_still_withdraw(client, organiser_headers) -> None:
    """Deleting what you sent is a privacy right, and it costs the
    withdrawer their score, so it is no loophole."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    token = _take(client, quiz, [{"question_id": qid, "answer_int": 7}]).json()["edit_token"]
    assert client.post(f"/api/v1/quizzes/by-token/{token}/withdraw").status_code == 204
    with SessionLocal() as db:
        assert db.query(FormSubmission).filter(FormSubmission.edit_token_hash.is_not(None)).count() >= 0
        assert client.get(f"/api/v1/quizzes/by-token/{token}").status_code == 404


# --- the organiser's side ---------------------------------------------


def test_the_organiser_sees_who_scored_what(client, organiser_headers) -> None:
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 2, "correct_int": 7}])
    qid = client.get(f"/api/v1/quizzes/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    _take(client, quiz, [{"question_id": qid, "answer_int": 7}], name="Sam")
    _take(client, quiz, [{"question_id": qid, "answer_int": 1}], name="Kim")

    rows = client.get(f"/api/v1/quizzes/{quiz['id']}/submissions", headers=organiser_headers).json()
    assert {(r["display_name"], r["score"], r["max_score"]) for r in rows} == {("Sam", 2, 2), ("Kim", 0, 2)}

    summary = client.get(f"/api/v1/quizzes/{quiz['id']}/summary", headers=organiser_headers).json()
    assert summary["submission_count"] == 2
    assert summary["score_average"] == 1.0
    assert summary["score_best"] == 2
    assert summary["max_score"] == 2
    # Which question was broken: half the room got this one.
    assert summary["questions"][0]["correct_share"] == 0.5


def test_a_survey_has_no_score_anywhere(client, organiser_headers) -> None:
    """The other half of the shared table: none of this leaks into a
    questionnaire."""
    r = client.post(
        "/api/v1/forms",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Gewone vragenlijst",
            "locale": "nl",
            "questions": [{"kind": "number", "prompt": "Leeftijd?", "points": 5, "correct_int": 30}],
        },
    )
    form = r.json()
    # The key was dropped on write: a survey has no answers to be right.
    assert form["questions"][0]["points"] == 0
    assert form["questions"][0]["correct_int"] is None
    qid = form["questions"][0]["id"]
    client.post(
        f"/api/v1/forms/by-slug/{form['slug']}/submit",
        json={"display_name": None, "answers": [{"question_id": qid, "answer_int": 30}]},
    )
    with SessionLocal() as db:
        assert db.query(FormSubmission).filter(FormSubmission.form_id == form["id"]).one().score is None
        assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).one().awarded is None
    summary = client.get(f"/api/v1/forms/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["score_average"] is None
    assert summary["questions"][0]["correct_share"] is None


# --- saving a quiz that cannot be graded ------------------------------


def test_a_scored_question_needs_an_answer(client, organiser_headers) -> None:
    """Checked when the organiser saves, not when somebody submits: at
    submit time the person who can fix it is not the person looking at
    the screen."""
    r = client.post(
        "/api/v1/quizzes",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Kapotte quiz",
            "locale": "nl",
            "questions": [{"kind": "short_text", "prompt": "Wie?", "points": 3}],
        },
    )
    assert r.status_code == 400


def test_a_correct_option_has_to_be_one_of_the_options(client, organiser_headers) -> None:
    r = client.post(
        "/api/v1/quizzes",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Kapotte quiz",
            "locale": "nl",
            "questions": [
                {
                    "kind": "single_choice",
                    "prompt": "Welke?",
                    "points": 1,
                    "options": ["A", "B"],
                    "correct_choices": ["C"],
                }
            ],
        },
    )
    assert r.status_code == 400


def test_a_quiz_is_a_row_in_the_forms_table(client, organiser_headers) -> None:
    """Stated once, here, because everything else in this file reads as
    if quizzes had their own tables. They do not, and the mode is what
    keeps the two products apart (docs/design-quizzes.md part 1)."""
    quiz = _quiz(client, organiser_headers, [])
    with SessionLocal() as db:
        assert db.get(Form, quiz["id"]).mode == "quiz"
