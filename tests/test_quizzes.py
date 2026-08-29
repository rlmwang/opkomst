"""A quiz is a questionnaire with a right answer.

What is tested here is only the part that differs (``docs/design-
quizzes.md``): the key, the grading, the score that outlives an edit,
and the two doors that are deliberately shut. Everything else about a
quiz is a form, and is covered by the forms suites through the same
code.

The grading rules, in one place, because each of them is a decision:

* a wrong answer and an unanswered optional question are both worth
  nothing;
* multi-choice pays part marks and charges for wrong ticks;
* a number may carry a tolerance;
* the two free-text kinds are refused outright: a quiz asks only what
  it can mark.
"""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import Form
from tests._helpers.forms import option_ids


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
    r = client.post("/api/v1/quiz", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _take(client: Any, quiz: dict[str, Any], answers: list[dict[str, Any]], name: str | None = "Sam") -> Any:
    return client.post(
        f"/api/v1/quiz/by-slug/{quiz['slug']}/submit",
        json={"display_name": name, "answers": answers},
    )


# --- the key and the score -------------------------------------------


def test_a_right_answer_scores_and_a_wrong_one_does_not(client, organiser_headers) -> None:
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Hoofdstad?",
                "points": 3,
                "options": [{"label": "Rotterdam"}, {"label": "Amsterdam", "is_correct": True}],
            },
            {"kind": "number", "prompt": "Hoeveel provincies?", "points": 2, "correct_int": 12},
        ],
    )
    qs = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"]
    r = _take(
        client,
        quiz,
        [
            {"question_id": qs[0]["id"], "answer_choices": option_ids(qs[0], "Amsterdam")},
            {"question_id": qs[1]["id"], "answer_int": 11},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["score"], body["max_score"]) == (3, 5)
    by_q = {a["question_id"]: a for a in body["answers"]}
    assert by_q[qs[0]["id"]]["correct"] is True
    assert by_q[qs[1]["id"]]["correct"] is False


def test_multi_choice_pays_part_marks_and_charges_for_wrong_ones(client, organiser_headers) -> None:
    """``(right ticks - wrong ticks) / right options``, rounded down.

    One wrong tick cancels one right tick: a pick is worth the same
    whichever way it goes (docs/design-quizzes.md part 1.3)."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "multi_choice",
                "prompt": "Welke twee?",
                "points": 6,
                "options": [
                    {"label": "A", "is_correct": True},
                    {"label": "B", "is_correct": True},
                    {"label": "C"},
                    {"label": "D"},
                ],
            }
        ],
    )
    question = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]
    qid = question["id"]

    def score(choices: list[str]) -> int:
        picked = option_ids(question, *choices)
        return _take(client, quiz, [{"question_id": qid, "answer_choices": picked}]).json()["score"]

    assert score(["A", "B"]) == 6  # (2 - 0) / 2
    assert score(["A"]) == 3  # (1 - 0) / 2
    assert score(["A", "B", "C"]) == 3  # (2 - 1) / 2
    assert score(["A", "C"]) == 0  # (1 - 1) / 2
    assert score(["A", "B", "C", "D"]) == 0  # (2 - 2) / 2, the whole point
    assert score(["C", "D"]) == 0  # clamped, never negative


def test_a_wrong_tick_costs_what_a_right_one_pays(client, organiser_headers) -> None:
    """The property the formula was chosen for, on a question with one
    right option among five: adding a wrong tick wipes out the right
    one exactly, however many wrong options there happen to be."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "multi_choice",
                "prompt": "Welke?",
                "points": 8,
                "options": [
                    {"label": "A", "is_correct": True},
                    {"label": "B"},
                    {"label": "C"},
                    {"label": "D"},
                    {"label": "E"},
                ],
            }
        ],
    )
    question = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]
    qid = question["id"]

    def score(choices: list[str]) -> int:
        picked = option_ids(question, *choices)
        return _take(client, quiz, [{"question_id": qid, "answer_choices": picked}]).json()["score"]

    assert score(["A"]) == 8
    assert score(["A", "B"]) == 0
    assert score(["A", "B", "C", "D", "E"]) == 0


def test_a_number_may_be_close_enough(client, organiser_headers) -> None:
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoe hoog?", "points": 2, "correct_int": 100, "tolerance": 5}],
    )
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    assert _take(client, quiz, [{"question_id": qid, "answer_int": 96}]).json()["score"] == 2
    assert _take(client, quiz, [{"question_id": qid, "answer_int": 94}]).json()["score"] == 0


def test_a_quiz_refuses_a_question_it_cannot_mark(client, organiser_headers) -> None:
    """Both free-text kinds are out. No rule grades a paragraph, and an
    exact-match short answer is a quiz about spelling rather than about
    knowing the answer, so the organiser is told at save time instead of
    finding out that a question quietly counted for nothing."""
    for kind in ("text", "short_text"):
        r = client.post(
            "/api/v1/quiz",
            headers=organiser_headers,
            json={
                "chapter_id": _chapter_id(client, organiser_headers),
                "name_nl": "Open vraag",
                "locale": "nl",
                "questions": [{"kind": kind, "prompt": "Waarom?", "points": 0}],
            },
        )
        assert r.status_code == 400, f"{kind}: {r.text}"


def test_a_questionnaire_still_takes_both_text_kinds(client, organiser_headers) -> None:
    """The restriction is the quiz's, not the table's."""
    r = client.post(
        "/api/v1/form",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Vragenlijst",
            "locale": "nl",
            "questions": [
                {"kind": "text", "prompt": "Waarom?"},
                {"kind": "short_text", "prompt": "Wie?"},
            ],
        },
    )
    assert r.status_code == 201, r.text


def test_every_quiz_question_is_required(client, organiser_headers) -> None:
    """Optional is not a thing a quiz has: skipping a question would be
    a free zero. The server decides it, so a payload that asks for
    optional gets required anyway."""
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoeveel?", "points": 3, "correct_int": 7, "required": False}],
    )
    assert quiz["questions"][0]["required"] is True
    # And the submit enforces it, the same way it does on a form.
    assert _take(client, quiz, []).status_code == 400


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
                "options": [{"label": "Rotterdam"}, {"label": "Zwolle", "is_correct": True}],
            },
            {"kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 42, "tolerance": 2},
        ],
    )
    response = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}")
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
        "step",
        # The margin is the rule the answer is marked by, not the
        # answer: a guess-the-number question that hides its own margin
        # asks people to guess the rules too.
        "tolerance",
    }
    for q in response.json()["questions"]:
        assert set(q) == allowed, sorted(set(q) - allowed)
    # The one key value distinctive enough to grep for safely.
    assert "Zwolle" not in response.text.split('"options"')[0]
    # And what it may carry.
    assert [o["label"] for o in response.json()["questions"][0]["options"]] == ["Rotterdam", "Zwolle"]


def test_the_result_reveals_the_key_only_when_the_quiz_says_so(client, organiser_headers) -> None:
    """An organiser running the same quiz twice in one evening turns
    the reveal off; the score still arrives."""
    questions = [{"kind": "number", "prompt": "In welk jaar?", "points": 1, "correct_int": 1894}]
    open_quiz = _quiz(client, organiser_headers, questions)
    closed_quiz = _quiz(client, organiser_headers, questions, reveal_answers=False)

    qid = client.get(f"/api/v1/quiz/by-slug/{open_quiz['slug']}").json()["questions"][0]["id"]
    revealed = _take(client, open_quiz, [{"question_id": qid, "answer_int": 1900}]).json()
    assert revealed["reveal_answers"] is True
    assert revealed["answers"][0]["correct_int"] == 1894

    qid = client.get(f"/api/v1/quiz/by-slug/{closed_quiz['slug']}").json()["questions"][0]["id"]
    hidden = _take(client, closed_quiz, [{"question_id": qid, "answer_int": 1900}]).json()
    assert hidden["reveal_answers"] is False
    assert hidden["answers"][0]["correct_int"] is None
    assert hidden["answers"][0]["correct"] is False


# --- the score outlives the quiz --------------------------------------


def test_a_score_follows_the_quiz_when_it_changes(client, organiser_headers) -> None:
    """Scores are derived, not stored. An organiser who re-weights a
    question, or fixes a key they got wrong, means every score to move
    with it: the answers are what was kept, and marking them again is
    what a score is."""
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoeveel?", "points": 1, "correct_int": 7}],
    )
    qs = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"]
    result = _take(client, quiz, [{"question_id": qs[0]["id"], "answer_int": 7}]).json()
    assert (result["score"], result["max_score"]) == (1, 1)

    saved = client.get(f"/api/v1/quiz/{quiz['id']}", headers=organiser_headers).json()
    client.put(
        f"/api/v1/quiz/{quiz['id']}",
        headers=organiser_headers,
        json={
            "chapter_id": saved["chapter_id"],
            "name_nl": "Pubquiz",
            "locale": "nl",
            "questions": [
                # Worth five now instead of one.
                {"id": qs[0]["id"], "kind": "number", "prompt": "Hoeveel?", "points": 5, "correct_int": 7},
                {"kind": "number", "prompt": "En nu?", "points": 4, "correct_int": 3},
            ],
        },
    )
    again = client.get(f"/api/v1/quiz/by-token/{result['edit_token']}").json()
    # Five for the answer that is still right, out of the nine the quiz
    # is now worth. The question added afterwards is not in the list:
    # this person never saw it.
    assert (again["score"], again["max_score"]) == (5, 9)
    assert len(again["answers"]) == 1

    # The organiser's page agrees, because it marks the same way.
    summary = client.get(f"/api/v1/quiz/{quiz['id']}/summary", headers=organiser_headers).json()
    assert (summary["score_average"], summary["score_best"], summary["max_score"]) == (5.0, 5, 9)
    rows = client.get(f"/api/v1/quiz/{quiz['id']}/submissions", headers=organiser_headers).json()
    assert (rows[0]["score"], rows[0]["max_score"]) == (5, 9)


def test_fixing_a_wrong_key_corrects_everybody(client, organiser_headers) -> None:
    """The other half of deriving: a key typed wrong is fixed once, and
    the people who answered correctly stop being marked wrong."""
    quiz = _quiz(
        client,
        organiser_headers,
        [{"kind": "number", "prompt": "Hoeveel provincies?", "points": 2, "correct_int": 11}],
    )
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    token = _take(client, quiz, [{"question_id": qid, "answer_int": 12}]).json()["edit_token"]
    assert client.get(f"/api/v1/quiz/by-token/{token}").json()["score"] == 0

    saved = client.get(f"/api/v1/quiz/{quiz['id']}", headers=organiser_headers).json()
    client.put(
        f"/api/v1/quiz/{quiz['id']}",
        headers=organiser_headers,
        json={
            "chapter_id": saved["chapter_id"],
            "name_nl": "Pubquiz",
            "locale": "nl",
            "questions": [
                {"id": qid, "kind": "number", "prompt": "Hoeveel provincies?", "points": 2, "correct_int": 12}
            ],
        },
    )
    assert client.get(f"/api/v1/quiz/by-token/{token}").json()["score"] == 2


def test_a_question_is_worth_one_point_unless_told_otherwise(client, organiser_headers) -> None:
    """Questions are worth the same until somebody decides otherwise,
    and a quiz where every question is worth nothing is nobody's
    intention. Zero stays expressible; it has to be typed."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {"kind": "number", "prompt": "Zonder punten?", "correct_int": 1},
            {"kind": "number", "prompt": "Met punten?", "points": 4, "correct_int": 2},
            {"kind": "number", "prompt": "Nul punten?", "points": 0, "correct_int": 3},
        ],
    )
    assert [q["points"] for q in quiz["questions"]] == [1, 4, 0]


# --- the doors that are shut ------------------------------------------


def test_a_taken_quiz_cannot_be_answered_again(client, organiser_headers) -> None:
    """Editing an answer after seeing the score is a second attempt.
    The token opens the result and nothing else."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    token = _take(client, quiz, [{"question_id": qid, "answer_int": 1}]).json()["edit_token"]
    r = client.put(
        f"/api/v1/quiz/by-token/{token}",
        json={"display_name": "Sam", "answers": [{"question_id": qid, "answer_int": 7}]},
    )
    assert r.status_code == 405


def test_a_taker_can_still_withdraw(client, organiser_headers) -> None:
    """Deleting what you sent is a privacy right, and it costs the
    withdrawer their score, so it is no loophole."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    token = _take(client, quiz, [{"question_id": qid, "answer_int": 7}]).json()["edit_token"]
    assert client.post(f"/api/v1/quiz/by-token/{token}/withdraw").status_code == 204
    # The answers are gone, so there is nothing left to mark: the token
    # resolves to nothing at all.
    assert client.get(f"/api/v1/quiz/by-token/{token}").status_code == 404


# --- the organiser's side ---------------------------------------------


def test_the_organiser_sees_who_scored_what(client, organiser_headers) -> None:
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 2, "correct_int": 7}])
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    _take(client, quiz, [{"question_id": qid, "answer_int": 7}], name="Sam")
    _take(client, quiz, [{"question_id": qid, "answer_int": 1}], name="Kim")

    rows = client.get(f"/api/v1/quiz/{quiz['id']}/submissions", headers=organiser_headers).json()
    assert {(r["display_name"], r["score"], r["max_score"]) for r in rows} == {("Sam", 2, 2), ("Kim", 0, 2)}

    summary = client.get(f"/api/v1/quiz/{quiz['id']}/summary", headers=organiser_headers).json()
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
        "/api/v1/form",
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
        f"/api/v1/form/by-slug/{form['slug']}/submit",
        json={"display_name": None, "answers": [{"question_id": qid, "answer_int": 30}]},
    )
    summary = client.get(f"/api/v1/form/{form['id']}/summary", headers=organiser_headers).json()
    assert summary["score_average"] is None
    assert summary["questions"][0]["correct_share"] is None


# --- saving a quiz that cannot be graded ------------------------------


def test_a_scored_question_needs_an_answer(client, organiser_headers) -> None:
    """Checked when the organiser saves, not when somebody submits: at
    submit time the person who can fix it is not the person looking at
    the screen."""
    r = client.post(
        "/api/v1/quiz",
        headers=organiser_headers,
        json={
            "chapter_id": _chapter_id(client, organiser_headers),
            "name_nl": "Kapotte quiz",
            "locale": "nl",
            "questions": [{"kind": "number", "prompt": "Hoeveel?", "points": 3}],
        },
    )
    assert r.status_code == 400


def test_a_correct_option_has_to_be_one_of_the_options(client, organiser_headers) -> None:
    r = client.post(
        "/api/v1/quiz",
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
                    "options": [{"label": "A"}, {"label": "B"}],
                }
            ],
        },
    )
    assert r.status_code == 400


def test_a_quiz_is_a_row_in_the_forms_table(client, organiser_headers) -> None:
    """Stated once, here, because everything else in this file reads as
    if quizzes had their own tables. They do not, and the mode is what
    keeps the two products apart (docs/design-quizzes.md part 1)."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    with SessionLocal() as db:
        assert db.get(Form, quiz["id"]).mode == "quiz"


def test_the_qr_points_at_the_quiz_and_not_at_a_form(client, organiser_headers) -> None:
    """The QR is the whole point of a quiz on a table in a pub. Both
    products share the endpoint, so the prefix has to come from the
    mount rather than from a constant: it pointed at /f/{slug} for
    everything, which for a quiz is a page that does not exist."""
    quiz = _quiz(client, organiser_headers, [{"kind": "number", "prompt": "?", "points": 1, "correct_int": 7}])
    response = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}/qr.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg")
    # The image encodes the URL as modules rather than as text, so what
    # is checked is the input to it: the same slug under the other
    # product's prefix is a different code, and the form endpoint does
    # not serve this slug at all.
    assert client.get(f"/api/v1/form/by-slug/{quiz['slug']}/qr.svg").status_code == 410
    from backend.routers.forms_public import PUBLIC_BASE_URL
    from backend.services.qr import render_qr

    assert response.content == render_qr(f"{PUBLIC_BASE_URL}/q/{quiz['slug']}")
    assert response.content != render_qr(f"{PUBLIC_BASE_URL}/f/{quiz['slug']}")


def test_ticking_nothing_is_an_answer_on_a_quiz(client, organiser_headers) -> None:
    """ "None of these" is a position. Every quiz question is required,
    so refusing an empty multiple-choice answer would leave somebody
    stuck on a question they have answered; it is accepted and marked
    like any other, which here is zero."""
    quiz = _quiz(
        client,
        organiser_headers,
        [
            {
                "kind": "multi_choice",
                "prompt": "Welke?",
                "points": 4,
                "options": [{"label": "A", "is_correct": True}, {"label": "B"}],
            }
        ],
    )
    qid = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]["id"]
    r = _take(client, quiz, [{"question_id": qid, "answer_choices": []}])
    assert r.status_code == 201, r.text
    assert r.json()["score"] == 0
    # And it is on the result screen as an answered question, not a
    # missing one.
    assert len(r.json()["answers"]) == 1
