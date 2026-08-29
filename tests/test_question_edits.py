"""Editing a question after people have answered it.

The matrix from ``docs/design-question-edits.md``, one test per thing an
organiser can do to a question or an option once answers exist. Every
one of these used to have an answer, and most of them used to lose it
silently: a rename detached every answer to the option, and a kind
change left them on disk where no surface could read them.

Two rules run through all of it:

* an option is a row, so a rename is an edit to its label and the
  answers stay pointed at it;
* a kind change is a different question, so it deletes and re-inserts,
  and its answers go with the row it replaced.

The kompas and quiz cases are the sharp ones. A kompas answer that stops
counting moves somebody's dot to 0.0, which the map draws dead centre,
so a silent failure there misreports a real person's position rather
than just losing a tally.
"""

from __future__ import annotations

from typing import Any

from tests._helpers.events import public_option_ids
from tests._helpers.forms import answer_cells, option_ids

AXES = [
    {"axis": "x", "name": "Economie", "low_name": "Links", "high_name": "Rechts"},
    {"axis": "y", "name": "Cultuur", "low_name": "Open", "high_name": "Behoud"},
]

_EVENT_BASE: dict[str, Any] = {
    "name_nl": "Buurtavond",
    "topic_nl": None,
    "location": "Buurthuis",
    "starts_on": "2027-05-01",
    "start_time": "18:00:00",
    "end_time": "20:00:00",
    "period_weeks": 1,
    "cycle_slots": [],
    "span_weeks": None,
    "horizon_days": 90,
    "feedback_enabled": False,
    "reminder_enabled": False,
    "listed": True,
    "locale": "nl",
}


def _chapter(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


# --- forms ------------------------------------------------------------


def _form(client: Any, headers: Any, questions: list[dict[str, Any]], mode: str = "form", **extra: Any) -> Any:
    body = {
        "chapter_id": _chapter(client, headers),
        "name_nl": "Vragenlijst",
        "locale": "nl",
        "questions": questions,
        **extra,
    }
    r = client.post(f"/api/v1/{mode}", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _answer(client: Any, form: dict[str, Any], labels: list[str], mode: str = "form") -> Any:
    """Submit one fill-in, naming choices by the label a person reads."""
    question = client.get(f"/api/v1/{mode}/by-slug/{form['slug']}").json()["questions"][0]
    r = client.post(
        f"/api/v1/{mode}/by-slug/{form['slug']}/submit",
        json={
            "display_name": "Sam",
            "answers": [{"question_id": question["id"], "answer_choices": option_ids(question, *labels)}],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r


def _save(client: Any, headers: Any, form: dict[str, Any], mutate, mode: str = "form", **extra: Any) -> Any:
    """Re-save the form with ``mutate`` applied to its questions. The
    payload carries the ids the GET returned, which is what an editor
    that preserves them does."""
    full = client.get(f"/api/v1/{mode}/{form['id']}", headers=headers).json()
    questions = full["questions"]
    mutate(questions)
    body = {
        "name_nl": full["name_nl"],
        "locale": full["locale"],
        "chapter_id": full["chapter_id"],
        "questions": questions,
        **extra,
    }
    return client.put(f"/api/v1/{mode}/{form['id']}", headers=headers, json=body)


def _counts(client: Any, headers: Any, form: dict[str, Any], mode: str = "form") -> tuple[dict[str, int], int]:
    question = client.get(f"/api/v1/{mode}/{form['id']}/summary", headers=headers).json()["questions"][0]
    return question["choice_counts"], question["response_count"]


_CHOICE = [
    {
        "kind": "single_choice",
        "prompt": "Hoe vaak kom je?",
        "required": True,
        "options": [{"label": "Wekelijks"}, {"label": "Maandelijks"}],
    }
]


def test_renaming_an_option_keeps_the_answers_to_it(client, organiser_headers) -> None:
    """The one that was silently wrong. Fixing a typo used to leave the
    renamed option reading zero, the CSV showing the old wording, and the
    response count disagreeing with the counts beside it."""
    form = _form(client, organiser_headers, _CHOICE)
    for labels in (["Wekelijks"], ["Wekelijks"], ["Maandelijks"]):
        _answer(client, form, labels)
    assert _counts(client, organiser_headers, form) == ({"Wekelijks": 2, "Maandelijks": 1}, 3)

    def rename(questions):
        questions[0]["options"][0]["label"] = "Elke week"

    assert _save(client, organiser_headers, form, rename).status_code == 200

    counts, total = _counts(client, organiser_headers, form)
    assert counts == {"Elke week": 2, "Maandelijks": 1}
    assert total == 3
    assert sum(counts.values()) == total
    # The export follows too: it prints the option as it reads now.
    assert answer_cells(client, organiser_headers, form) == [["Elke week"], ["Elke week"], ["Maandelijks"]]


def test_reordering_options_keeps_every_count(client, organiser_headers) -> None:
    form = _form(client, organiser_headers, _CHOICE)
    for labels in (["Wekelijks"], ["Maandelijks"]):
        _answer(client, form, labels)

    def reorder(questions):
        questions[0]["options"].reverse()

    assert _save(client, organiser_headers, form, reorder).status_code == 200
    counts, total = _counts(client, organiser_headers, form)
    assert counts == {"Maandelijks": 1, "Wekelijks": 1}
    assert total == 2


def test_adding_an_option_leaves_the_existing_answers_alone(client, organiser_headers) -> None:
    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])

    def add(questions):
        questions[0]["options"].append({"label": "Nooit"})

    assert _save(client, organiser_headers, form, add).status_code == 200
    counts, total = _counts(client, organiser_headers, form)
    assert counts == {"Wekelijks": 1, "Maandelijks": 0, "Nooit": 0}
    assert total == 1


def test_deleting_an_answered_option_takes_its_answers(client, organiser_headers) -> None:
    """Removing an option removes what was said with it. That is the
    destructive edit the design gates behind a confirmation; this test
    pins what it does, not whether it asked first."""
    form = _form(
        client,
        organiser_headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Hoe vaak kom je?",
                "required": True,
                "options": [{"label": "Wekelijks"}, {"label": "Maandelijks"}, {"label": "Nooit"}],
            }
        ],
    )
    _answer(client, form, ["Wekelijks"])
    _answer(client, form, ["Maandelijks"])

    def drop_answered(questions):
        questions[0]["options"] = [o for o in questions[0]["options"] if o["label"] != "Wekelijks"]

    assert _save(client, organiser_headers, form, drop_answered, confirm_destructive=True).status_code == 200
    counts, total = _counts(client, organiser_headers, form)
    assert "Wekelijks" not in counts
    assert counts == {"Maandelijks": 1, "Nooit": 0}
    # The answer to the removed option is gone rather than stranded, so
    # the count and the tally still agree.
    assert total == 1


def test_editing_the_prompt_keeps_the_answers(client, organiser_headers) -> None:
    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])

    def reword(questions):
        questions[0]["prompt"] = "Hoe vaak kom je langs?"

    assert _save(client, organiser_headers, form, reword).status_code == 200
    assert _counts(client, organiser_headers, form) == ({"Wekelijks": 1, "Maandelijks": 0}, 1)


def test_changing_the_kind_replaces_the_question_and_its_answers(client, organiser_headers, db) -> None:
    """A rating question is not the multiple-choice question people
    answered, so the row is replaced and its answers go. The other
    question on the form keeps its own."""
    from backend.models import FormResponse

    form = _form(
        client,
        organiser_headers,
        [
            *_CHOICE,
            {"kind": "short_text", "prompt": "Waarom?", "required": False},
        ],
    )
    questions = client.get(f"/api/v1/form/by-slug/{form['slug']}").json()["questions"]
    for _ in range(2):
        r = client.post(
            f"/api/v1/form/by-slug/{form['slug']}/submit",
            json={
                "display_name": "Sam",
                "answers": [
                    {"question_id": questions[0]["id"], "answer_choices": option_ids(questions[0], "Wekelijks")},
                    {"question_id": questions[1]["id"], "answer_text": "omdat"},
                ],
            },
        )
        assert r.status_code in (200, 201), r.text
    assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).count() == 4

    before = client.get(f"/api/v1/form/{form['id']}", headers=organiser_headers).json()["questions"][0]["id"]

    def to_rating(qs):
        qs[0].update({"kind": "rating", "options": []})

    assert _save(client, organiser_headers, form, to_rating, confirm_destructive=True).status_code == 200
    db.expire_all()

    after = client.get(f"/api/v1/form/{form['id']}", headers=organiser_headers).json()["questions"]
    assert after[0]["kind"] == "rating"
    # A different question, so a different id.
    assert after[0]["id"] != before
    # Its two answers went; the open question's two stayed.
    assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).count() == 2
    # The retyped question's column is empty; the open question kept its answers.
    assert answer_cells(client, organiser_headers, form) == [["", "omdat"], ["", "omdat"]]


def test_retyping_a_question_drops_its_answers(client, organiser_headers, db) -> None:
    """An editor that discards the id is asking for a new question. This
    is the case ids cannot defend against, which is why the editor has to
    preserve them (``docs/design-question-edits.md``, decision 4)."""
    from backend.models import FormResponse

    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])
    assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).count() == 1

    def retype(questions):
        questions[0].pop("id")
        for option in questions[0]["options"]:
            option.pop("id")

    assert _save(client, organiser_headers, form, retype, confirm_destructive=True).status_code == 200
    db.expire_all()
    assert db.query(FormResponse).filter(FormResponse.form_id == form["id"]).count() == 0


# --- kompas -----------------------------------------------------------


def _kompas(client: Any, headers: Any) -> Any:
    return _form(
        client,
        headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Waar sta je?",
                "required": True,
                "options": [
                    {"label": "Meer markt", "pole": "x_high"},
                    {"label": "Meer collectief", "pole": "x_low"},
                ],
            },
            {"kind": "rating", "prompt": "Cultuur?", "required": True, "pole": "y_high"},
        ],
        mode="compass",
        axes=AXES,
    )


def _place(client: Any, kompas: dict[str, Any], choice: str) -> Any:
    questions = client.get(f"/api/v1/compass/by-slug/{kompas['slug']}").json()["questions"]
    r = client.post(
        f"/api/v1/compass/by-slug/{kompas['slug']}/submit",
        json={
            "display_name": "Ada",
            "answers": [
                {"question_id": questions[0]["id"], "answer_choices": option_ids(questions[0], choice)},
                {"question_id": questions[1]["id"], "answer_int": 3},
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r


def _dots(client: Any, headers: Any, kompas: dict[str, Any]) -> list[tuple[str, float, float]]:
    summary = client.get(f"/api/v1/compass/{kompas['id']}/summary", headers=headers).json()
    return [(p["name"], p["x"], p["y"]) for p in summary["compass"]["points"]]


def test_renaming_a_kompas_option_leaves_the_dot_where_it_was(client, organiser_headers) -> None:
    """The sharpest case. A lost kompas answer does not read as missing,
    it reads as neutral: the dot lands at 0.0, dead centre of the map,
    and somebody who took a side is displayed as a moderate."""
    kompas = _kompas(client, organiser_headers)
    _place(client, kompas, "Meer collectief")
    assert _dots(client, organiser_headers, kompas) == [("Ada", -1.0, 0.0)]

    def rename(questions):
        questions[0]["options"][1]["label"] = "Collectiever"

    assert _save(client, organiser_headers, kompas, rename, mode="compass", axes=AXES).status_code == 200
    assert _dots(client, organiser_headers, kompas) == [("Ada", -1.0, 0.0)]


def test_moving_a_kompas_option_to_the_other_side_moves_the_dot(client, organiser_headers) -> None:
    """The edit that is *meant* to move people. Positions are derived
    from the answers, so redefining what an option means redraws the map,
    which is what the organiser asked for."""
    kompas = _kompas(client, organiser_headers)
    _place(client, kompas, "Meer collectief")
    assert _dots(client, organiser_headers, kompas) == [("Ada", -1.0, 0.0)]

    def flip(questions):
        questions[0]["options"][0]["pole"] = "x_low"
        questions[0]["options"][1]["pole"] = "x_high"

    assert _save(client, organiser_headers, kompas, flip, mode="compass", axes=AXES).status_code == 200
    assert _dots(client, organiser_headers, kompas) == [("Ada", 1.0, 0.0)]


def test_reordering_kompas_options_does_not_move_anybody(client, organiser_headers) -> None:
    """Directions used to be a list parallel to the options, read by
    position, so reordering could hand an answer somebody else's
    meaning. Each option carries its own now."""
    kompas = _kompas(client, organiser_headers)
    _place(client, kompas, "Meer collectief")

    def reorder(questions):
        questions[0]["options"].reverse()

    assert _save(client, organiser_headers, kompas, reorder, mode="compass", axes=AXES).status_code == 200
    assert _dots(client, organiser_headers, kompas) == [("Ada", -1.0, 0.0)]


# --- quiz -------------------------------------------------------------


def _quiz(client: Any, headers: Any) -> Any:
    return _form(
        client,
        headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Welke stad?",
                "required": True,
                "points": 5,
                "options": [{"label": "Rotterdam"}, {"label": "Amsterdam", "is_correct": True}],
            }
        ],
        mode="quiz",
    )


def _score(client: Any, quiz: dict[str, Any], choice: str) -> int:
    question = client.get(f"/api/v1/quiz/by-slug/{quiz['slug']}").json()["questions"][0]
    r = client.post(
        f"/api/v1/quiz/by-slug/{quiz['slug']}/submit",
        json={
            "display_name": "Bo",
            "answers": [{"question_id": question["id"], "answer_choices": option_ids(question, choice)}],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["score"]


def test_renaming_a_quiz_option_does_not_change_what_was_scored(client, organiser_headers) -> None:
    quiz = _quiz(client, organiser_headers)
    assert _score(client, quiz, "Amsterdam") == 5

    def rename(questions):
        questions[0]["options"][1]["label"] = "Mokum"

    assert _save(client, organiser_headers, quiz, rename, mode="quiz").status_code == 200
    summary = client.get(f"/api/v1/quiz/{quiz['id']}/summary", headers=organiser_headers).json()
    assert summary["score_average"] == 5.0
    assert summary["questions"][0]["choice_counts"] == {"Rotterdam": 0, "Mokum": 1}


def test_changing_which_option_is_correct_rescores_everyone(client, organiser_headers) -> None:
    """Scores are derived, never stored, so fixing a wrong key corrects
    every score that was ever given. That is the documented intent."""
    quiz = _quiz(client, organiser_headers)
    assert _score(client, quiz, "Rotterdam") == 0
    assert client.get(f"/api/v1/quiz/{quiz['id']}/summary", headers=organiser_headers).json()["score_average"] == 0.0

    def fix_key(questions):
        questions[0]["options"][0]["is_correct"] = True
        questions[0]["options"][1]["is_correct"] = False

    assert _save(client, organiser_headers, quiz, fix_key, mode="quiz").status_code == 200
    assert client.get(f"/api/v1/quiz/{quiz['id']}/summary", headers=organiser_headers).json()["score_average"] == 5.0


# --- events -----------------------------------------------------------


def _event(client: Any, headers: Any) -> Any:
    r = client.post(
        "/api/v1/event",
        headers=headers,
        json={
            **_EVENT_BASE,
            "chapter_id": _chapter(client, headers),
            "source_options": [{"label": "Flyer"}, {"label": "Vriend"}],
            "source_enabled": True,
            "help_options": [{"label": "Opbouwen"}, {"label": "Afbreken"}],
            "help_enabled": True,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _sign_up(client: Any, event: dict[str, Any], source: str, help_labels: tuple[str, ...]) -> None:
    slug = event["next_slug"]
    r = client.post(
        f"/api/v1/event/by-slug/{slug}/signups",
        json={
            "display_name": "Aisha",
            "party_size": 2,
            **public_option_ids(client, slug, source=source, help_labels=help_labels),
            "all_upcoming": True,
        },
    )
    assert r.status_code == 201, r.text


def _breakdowns(client: Any, headers: Any, event: dict[str, Any]) -> tuple[dict[str, int], dict[str, int]]:
    occ = client.get(f"/api/v1/event/{event['id']}/occurrences", headers=headers).json()["occurrences"][0]
    stats = client.get(f"/api/v1/event/{event['id']}/occurrences/{occ['id']}/stats", headers=headers).json()
    return stats["by_source"], stats["by_help"]


def _save_event(client: Any, headers: Any, event: dict[str, Any], mutate, **extra: Any) -> Any:
    full = client.get(f"/api/v1/event/{event['id']}", headers=headers).json()
    mutate(full)
    return client.put(
        f"/api/v1/event/{event['id']}",
        headers=headers,
        json={
            **_EVENT_BASE,
            "chapter_id": full["chapter_id"],
            "source_options": full["source_options"],
            "source_enabled": True,
            "help_options": full["help_options"],
            "help_enabled": True,
            **extra,
        },
    )


def test_renaming_a_source_option_keeps_the_signups_that_picked_it(client, organiser_headers) -> None:
    """``by_source`` is grouped from what was stored, so a rename used to
    leave the old wording standing as a bucket of its own, naming an
    option the form no longer offered."""
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ())
    assert _breakdowns(client, organiser_headers, event)[0] == {"Flyer": 2}

    def rename(full):
        full["source_options"][0]["label"] = "Flyertje"

    assert _save_event(client, organiser_headers, event, rename).status_code == 200
    assert _breakdowns(client, organiser_headers, event)[0] == {"Flyertje": 2}


def test_renaming_a_help_option_keeps_the_offers_made_against_it(client, organiser_headers) -> None:
    """``by_help`` is seeded from the event's own list, so a rename used
    to read zero and the offers vanished from the page."""
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ("Opbouwen",))
    assert _breakdowns(client, organiser_headers, event)[1] == {"Opbouwen": 2, "Afbreken": 0}

    def rename(full):
        full["help_options"][0]["label"] = "Opbouw"

    assert _save_event(client, organiser_headers, event, rename).status_code == 200
    assert _breakdowns(client, organiser_headers, event)[1] == {"Opbouw": 2, "Afbreken": 0}


def test_deleting_a_source_option_leaves_the_signup_standing(client, organiser_headers) -> None:
    """The foreign key is ON DELETE SET NULL: the person still came, they
    just no longer have an answer to a question that is gone. Losing the
    sign-up along with the option would be worse than losing the answer."""
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ())
    occ = client.get(f"/api/v1/event/{event['id']}/occurrences", headers=organiser_headers).json()["occurrences"][0]

    def drop(full):
        full["source_options"] = [o for o in full["source_options"] if o["label"] != "Flyer"]

    assert _save_event(client, organiser_headers, event, drop, confirm_destructive=True).status_code == 200
    by_source, _ = _breakdowns(client, organiser_headers, event)
    assert "Flyer" not in by_source
    # Still one line item, still two people.
    signups = client.get(
        f"/api/v1/event/{event['id']}/occurrences/{occ['id']}/signups", headers=organiser_headers
    ).json()
    assert len(signups) == 1
    assert signups[0]["party_size"] == 2


def test_deleting_a_help_option_takes_the_offers_with_it(client, organiser_headers) -> None:
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ("Opbouwen", "Afbreken"))
    assert _breakdowns(client, organiser_headers, event)[1] == {"Opbouwen": 2, "Afbreken": 2}

    def drop(full):
        full["help_options"] = [o for o in full["help_options"] if o["label"] != "Opbouwen"]

    assert _save_event(client, organiser_headers, event, drop, confirm_destructive=True).status_code == 200
    assert _breakdowns(client, organiser_headers, event)[1] == {"Afbreken": 2}


def test_adding_an_event_option_leaves_the_existing_answers_alone(client, organiser_headers) -> None:
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ("Opbouwen",))

    def add(full):
        full["source_options"].append({"id": None, "label": "Poster"})

    assert _save_event(client, organiser_headers, event, add).status_code == 200
    by_source, by_help = _breakdowns(client, organiser_headers, event)
    assert by_source == {"Flyer": 2}
    assert by_help == {"Opbouwen": 2, "Afbreken": 0}


# --- the confirmation gate --------------------------------------------
#
# Decision 2: the three edits above that destroy answers are refused
# once, with a count, and go through when the same save comes back
# confirmed. Silently deleting what people said is the thing this stops.


def test_deleting_an_answered_option_is_refused_until_confirmed(client, organiser_headers) -> None:
    # Three options, so dropping one still leaves a choice question a
    # choice to offer and the refusal is the gate rather than the
    # two-option minimum.
    form = _form(
        client,
        organiser_headers,
        [
            {
                "kind": "single_choice",
                "prompt": "Hoe vaak kom je?",
                "required": True,
                "options": [{"label": "Wekelijks"}, {"label": "Maandelijks"}, {"label": "Nooit"}],
            }
        ],
    )
    _answer(client, form, ["Wekelijks"])
    _answer(client, form, ["Wekelijks"])

    def drop(questions):
        questions[0]["options"] = [o for o in questions[0]["options"] if o["label"] != "Wekelijks"]

    refused = _save(client, organiser_headers, form, drop)
    assert refused.status_code == 409
    assert "2 given answers" in refused.json()["detail"]
    # Refused means nothing moved.
    assert _counts(client, organiser_headers, form) == ({"Wekelijks": 2, "Maandelijks": 0, "Nooit": 0}, 2)

    confirmed = _save(client, organiser_headers, form, drop, confirm_destructive=True)
    assert confirmed.status_code == 200
    assert _counts(client, organiser_headers, form) == ({"Maandelijks": 0, "Nooit": 0}, 0)


def test_removing_a_question_is_refused_until_confirmed(client, organiser_headers) -> None:
    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])

    def remove(questions):
        questions.clear()
        questions.append({"kind": "short_text", "prompt": "Iets anders?", "required": False, "options": []})

    refused = _save(client, organiser_headers, form, remove)
    assert refused.status_code == 409
    assert "1 given answer" in refused.json()["detail"]
    assert _save(client, organiser_headers, form, remove, confirm_destructive=True).status_code == 200


def test_changing_the_kind_is_refused_until_confirmed(client, organiser_headers) -> None:
    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])

    def to_rating(questions):
        questions[0].update({"kind": "rating", "options": []})

    refused = _save(client, organiser_headers, form, to_rating)
    assert refused.status_code == 409
    assert _save(client, organiser_headers, form, to_rating, confirm_destructive=True).status_code == 200


def test_a_harmless_edit_needs_no_confirmation(client, organiser_headers) -> None:
    """The gate only stands in front of edits that destroy something.
    Renaming, reordering and adding go straight through, which is the
    whole point of options being rows."""
    form = _form(client, organiser_headers, _CHOICE)
    _answer(client, form, ["Wekelijks"])

    def harmless(questions):
        questions[0]["prompt"] = "Hoe vaak kom je langs?"
        questions[0]["options"][0]["label"] = "Elke week"
        questions[0]["options"].reverse()
        questions[0]["options"].append({"label": "Nooit"})

    assert _save(client, organiser_headers, form, harmless).status_code == 200
    counts, total = _counts(client, organiser_headers, form)
    assert counts == {"Maandelijks": 0, "Elke week": 1, "Nooit": 0}
    assert total == 1


def test_removing_an_answered_event_option_is_refused_until_confirmed(client, organiser_headers) -> None:
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ("Opbouwen",))

    def drop_both(full):
        full["source_options"] = [o for o in full["source_options"] if o["label"] != "Flyer"]
        full["help_options"] = [o for o in full["help_options"] if o["label"] != "Opbouwen"]

    refused = _save_event(client, organiser_headers, event, drop_both)
    assert refused.status_code == 409
    # One sign-up named the source and one offer was made against the
    # help option, so two answers would go.
    assert "2 given answers" in refused.json()["detail"]
    by_source, by_help = _breakdowns(client, organiser_headers, event)
    assert by_source == {"Flyer": 2} and by_help == {"Opbouwen": 2, "Afbreken": 0}

    assert _save_event(client, organiser_headers, event, drop_both, confirm_destructive=True).status_code == 200
    by_source, by_help = _breakdowns(client, organiser_headers, event)
    assert by_source == {} and by_help == {"Afbreken": 0}


def test_renaming_an_event_option_needs_no_confirmation(client, organiser_headers) -> None:
    event = _event(client, organiser_headers)
    _sign_up(client, event, "Flyer", ("Opbouwen",))

    def rename(full):
        full["source_options"][0]["label"] = "Flyertje"
        full["help_options"][0]["label"] = "Opbouw"

    assert _save_event(client, organiser_headers, event, rename).status_code == 200
