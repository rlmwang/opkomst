"""A kompas is a questionnaire that points somewhere.

What is tested here is only the part that differs
(``docs/design-kompas.md``): the direction on an answer, the position
that comes out of it, the map everybody lands on, and the refusals that
keep a half-written kompas from reaching a respondent. Everything else
about a kompas is a form, and is covered by the forms suites through
the same code.

The arithmetic, in one place, because each line of it is a decision:

* a rating poles the statement, and a 5 is all the way toward that
  side, a 1 all the way toward the other, a 3 the middle;
* a choice poles each option, and lands on one of the two ends;
* a position is the mean per axis, so an unbalanced kompas still reads
  on one scale;
* a 3 counts and pulls toward the centre; a skipped question does not
  count at all;
* nothing is stored, so moving an option moves every dot.
"""

from __future__ import annotations

from typing import Any

AXES = [
    {
        "axis": "x",
        "name": "Economie",
        "description": "Waar het geld heen gaat",
        "low_name": "Links",
        "high_name": "Rechts",
    },
    {
        "axis": "y",
        "name": "Cultuur",
        "low_name": "Open",
        "high_name": "Behoud",
    },
]


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _statement(prompt: str, pole: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "rating", "prompt": prompt, "pole": pole, **extra}


def _choice(prompt: str, pairs: list[tuple[str, str]], **extra: Any) -> dict[str, Any]:
    return {
        "kind": "single_choice",
        "prompt": prompt,
        "options": [text for text, _ in pairs],
        "option_poles": [pole for _, pole in pairs],
        **extra,
    }


def _create(client: Any, headers: Any, questions: list[dict[str, Any]], axes: Any = None, **extra: Any) -> Any:
    return client.post(
        "/api/v1/compasses",
        headers=headers,
        json={
            "chapter_id": _chapter_id(client, headers),
            "name_nl": "Waar sta jij?",
            "locale": "nl",
            "axes": AXES if axes is None else axes,
            "questions": questions,
            **extra,
        },
    )


def _compass(client: Any, headers: Any, questions: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    r = _create(client, headers, questions, **extra)
    assert r.status_code == 201, r.text
    return r.json()


def _fill(client: Any, kompas: dict[str, Any], answers: list[dict[str, Any]], name: str | None = "Sam") -> Any:
    return client.post(
        f"/api/v1/compasses/by-slug/{kompas['slug']}/submit",
        json={"display_name": name, "answers": answers},
    )


# --- what one answer is worth ----------------------------------------


def test_a_five_is_the_pole_and_a_one_is_its_opposite(client, organiser_headers) -> None:
    kompas = _compass(
        client,
        organiser_headers,
        [_statement("Meer huizen", "x_high"), _choice("Waarheen?", [("A", "y_low"), ("B", "y_high")])],
    )
    q = kompas["questions"][0]["id"]
    other = kompas["questions"][1]["id"]

    top = _fill(client, kompas, [{"question_id": q, "answer_int": 5}, {"question_id": other, "answer_choices": ["A"]}])
    assert top.status_code == 201, top.text
    assert top.json()["x"] == 1.0

    bottom = _fill(
        client, kompas, [{"question_id": q, "answer_int": 1}, {"question_id": other, "answer_choices": ["A"]}], "Kim"
    )
    assert bottom.json()["x"] == -1.0


def test_the_scale_steps_by_a_half_and_a_three_is_the_middle(client, organiser_headers) -> None:
    kompas = _compass(
        client,
        organiser_headers,
        [_statement("Meer huizen", "x_low"), _choice("Waarheen?", [("A", "y_low"), ("B", "y_high")])],
    )
    q, other = (row["id"] for row in kompas["questions"])
    for given, expected in ((1, 1.0), (2, 0.5), (3, 0.0), (4, -0.5), (5, -1.0)):
        r = _fill(
            client,
            kompas,
            [{"question_id": q, "answer_int": given}, {"question_id": other, "answer_choices": ["A"]}],
            f"n{given}",
        )
        # ``x_low`` flips the scale: a 5 is all the way toward Links,
        # which is the negative end.
        assert r.json()["x"] == expected, given


def test_a_chosen_option_lands_on_its_own_end(client, organiser_headers) -> None:
    kompas = _compass(
        client,
        organiser_headers,
        [_choice("Waarheen?", [("Links", "x_low"), ("Rechts", "x_high"), ("Behoud", "y_high")])],
    )
    q = kompas["questions"][0]["id"]
    assert _fill(client, kompas, [{"question_id": q, "answer_choices": ["Rechts"]}]).json()["x"] == 1.0
    assert _fill(client, kompas, [{"question_id": q, "answer_choices": ["Links"]}], "Kim").json()["x"] == -1.0
    off = _fill(client, kompas, [{"question_id": q, "answer_choices": ["Behoud"]}], "Bo").json()
    # An option on the other axis says nothing about x, so x is 0 and
    # says so: nothing counted toward it.
    assert (off["x"], off["counted_x"], off["y"], off["counted_y"]) == (0.0, 0, 1.0, 1)


# --- the position ----------------------------------------------------


def test_a_position_is_the_mean_so_an_unbalanced_kompas_still_reads(client, organiser_headers) -> None:
    """Three questions on x and one on y. A sum would make x the longer
    axis; a mean keeps both on the same scale."""
    kompas = _compass(
        client,
        organiser_headers,
        [
            _statement("Een", "x_high"),
            _statement("Twee", "x_high"),
            _statement("Drie", "x_low"),
            _statement("Vier", "y_high"),
        ],
    )
    ids = [q["id"] for q in kompas["questions"]]
    r = _fill(
        client,
        kompas,
        [
            {"question_id": ids[0], "answer_int": 5},
            {"question_id": ids[1], "answer_int": 4},
            {"question_id": ids[2], "answer_int": 1},
            {"question_id": ids[3], "answer_int": 5},
        ],
    )
    # +1.0, +0.5 and (1 against x_low) +1.0, meaned.
    assert r.json()["x"] == round((1.0 + 0.5 + 1.0) / 3, 3)
    assert r.json()["y"] == 1.0


def test_a_middle_answer_counts_and_a_skipped_one_does_not(client, organiser_headers) -> None:
    kompas = _compass(
        client,
        organiser_headers,
        [
            _statement("Een", "x_high"),
            _statement("Twee", "x_high", required=False),
            _statement("Drie", "y_high"),
        ],
    )
    ids = [q["id"] for q in kompas["questions"]]

    middled = _fill(
        client,
        kompas,
        [
            {"question_id": ids[0], "answer_int": 5},
            {"question_id": ids[1], "answer_int": 3},
            {"question_id": ids[2], "answer_int": 5},
        ],
    ).json()
    # A 3 is worth nothing and still counted, so it halves the mean.
    assert (middled["x"], middled["counted_x"]) == (0.5, 2)

    skipped = _fill(
        client,
        kompas,
        [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[2], "answer_int": 5}],
        "Kim",
    ).json()
    assert (skipped["x"], skipped["counted_x"]) == (1.0, 1)


def test_an_axis_nobody_answered_is_zero_and_says_so(client, organiser_headers) -> None:
    kompas = _compass(
        client,
        organiser_headers,
        [_statement("Een", "x_high", required=False), _statement("Twee", "y_high", required=False)],
    )
    ids = [q["id"] for q in kompas["questions"]]
    r = _fill(client, kompas, [{"question_id": ids[0], "answer_int": 4}]).json()
    assert (r["y"], r["counted_y"]) == (0.0, 0)


# --- nothing is stored -----------------------------------------------


def test_moving_an_option_to_the_other_side_moves_the_dot(client, organiser_headers) -> None:
    """The correction the quiz needed, designed in from the start: a
    position is the answers read against the kompas as it stands now."""
    kompas = _compass(
        client,
        organiser_headers,
        [_choice("Waarheen?", [("A", "x_low"), ("B", "x_high")]), _statement("Twee", "y_high")],
    )
    q, other = (row["id"] for row in kompas["questions"])
    filled = _fill(
        client, kompas, [{"question_id": q, "answer_choices": ["A"]}, {"question_id": other, "answer_int": 5}]
    ).json()
    assert filled["x"] == -1.0
    token = filled["edit_token"]

    body = dict(kompas)
    body["questions"] = [
        {**kompas["questions"][0], "option_poles": ["x_high", "x_low"]},
        kompas["questions"][1],
    ]
    body["axes"] = AXES
    r = client.put(f"/api/v1/compasses/{kompas['id']}", headers=organiser_headers, json=body)
    assert r.status_code == 200, r.text

    again = client.get(f"/api/v1/compasses/by-token/{token}")
    assert again.json()["x"] == 1.0


# --- the map ---------------------------------------------------------


def test_the_map_carries_everybody_and_marks_the_reader(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    answers = [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[1], "answer_int": 2}]
    _fill(client, kompas, answers, "Sam")
    mine = _fill(client, kompas, answers, None).json()

    assert len(mine["points"]) == 2
    assert [p["name"] for p in mine["points"]] == ["Sam", None]
    # Exactly one dot is the reader's own, and it is the one that was
    # just written.
    assert [p["you"] for p in mine["points"]] == [False, True]


def test_the_walk_never_learns_which_answer_points_where(client, organiser_headers) -> None:
    """The seam the quiz built for its answer key, reused: a kompas
    whose page says which button moves you where is one people answer
    to land somewhere (``docs/design-kompas.md`` 5.2)."""
    kompas = _compass(
        client,
        organiser_headers,
        [_statement("Een", "x_high"), _choice("Waarheen?", [("A", "y_low"), ("B", "y_high")])],
    )
    public = client.get(f"/api/v1/compasses/by-slug/{kompas['slug']}").json()
    for question in public["questions"]:
        assert "pole" not in question
        assert "option_poles" not in question
    # What the two axes are called is not a secret: the cover names it.
    assert [a["name"] for a in public["axes"]] == ["Economie", "Cultuur"]


def test_changing_your_mind_is_allowed_and_redraws_the_map(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    first = _fill(
        client,
        kompas,
        [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[1], "answer_int": 5}],
    ).json()
    token = first["edit_token"]

    changed = client.put(
        f"/api/v1/compasses/by-token/{token}",
        json={
            "display_name": "Kim",
            "answers": [
                {"question_id": ids[0], "answer_int": 1},
                {"question_id": ids[1], "answer_int": 5},
            ],
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["x"] == -1.0
    assert changed.json()["display_name"] == "Kim"
    assert [p["name"] for p in changed.json()["points"]] == ["Kim"]


def test_withdrawing_takes_the_dot_off_the_map(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    answers = [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[1], "answer_int": 5}]
    _fill(client, kompas, answers, "Sam")
    mine = _fill(client, kompas, answers, "Kim").json()

    assert client.post(f"/api/v1/compasses/by-token/{mine['edit_token']}/withdraw").status_code == 204
    summary = client.get(f"/api/v1/compasses/{kompas['id']}/summary", headers=organiser_headers).json()
    assert [p["name"] for p in summary["compass"]["points"]] == ["Sam"]


# --- what the organiser sees -----------------------------------------


def test_the_summary_says_where_the_room_sits_on_each_axis(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    for given, name in ((5, "Sam"), (3, "Kim")):
        _fill(
            client,
            kompas,
            [{"question_id": ids[0], "answer_int": given}, {"question_id": ids[1], "answer_int": 5}],
            name,
        )
    summary = client.get(f"/api/v1/compasses/{kompas['id']}/summary", headers=organiser_headers).json()
    x_axis = summary["compass"]["axes"][0]
    assert x_axis["axis"]["name"] == "Economie"
    # Two people, one at 1.0 and one at 0.0: the mean is 0.5 and two
    # answers say almost nothing about where the room is, so the
    # interval runs the whole axis (clamped: there is no outside).
    assert (x_axis["average"], x_axis["ci_low"], x_axis["ci_high"]) == (0.5, -1.0, 1.0)
    # And every question carries the direction that earned its counts.
    assert summary["questions"][0]["pole"] == "x_high"


def test_the_interval_narrows_as_the_room_agrees(client, organiser_headers) -> None:
    """It is a confidence interval and not a range, so more people who
    answer the same make it tighter rather than leaving it where the
    two extremes are."""
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]

    def x_axis() -> dict:
        summary = client.get(f"/api/v1/compasses/{kompas['id']}/summary", headers=organiser_headers).json()
        return summary["compass"]["axes"][0]

    for i in range(4):
        _fill(
            client,
            kompas,
            [{"question_id": ids[0], "answer_int": 5 if i % 2 else 4}, {"question_id": ids[1], "answer_int": 5}],
            f"P{i}",
        )
    narrow = x_axis()
    for i in range(4, 12):
        _fill(
            client,
            kompas,
            [{"question_id": ids[0], "answer_int": 5 if i % 2 else 4}, {"question_id": ids[1], "answer_int": 5}],
            f"P{i}",
        )
    narrower = x_axis()

    width = narrow["ci_high"] - narrow["ci_low"]
    assert narrower["ci_high"] - narrower["ci_low"] < width
    # The mean stays inside its own interval, on both counts.
    for row in (narrow, narrower):
        assert row["ci_low"] <= row["average"] <= row["ci_high"]


def test_one_answer_has_a_mean_and_no_interval(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    _fill(client, kompas, [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[1], "answer_int": 5}], "Sam")
    x_axis = client.get(f"/api/v1/compasses/{kompas['id']}/summary", headers=organiser_headers).json()["compass"][
        "axes"
    ][0]
    assert (x_axis["average"], x_axis["ci_low"], x_axis["ci_high"]) == (1.0, 1.0, 1.0)


def test_the_result_carries_the_room_as_well_as_you(client, organiser_headers) -> None:
    """The respondent's own bar is drawn against where the room sits, so
    the result carries the same axis stats the organiser's page reads."""
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    for given, name in ((5, "Sam"), (4, "Kim"), (4, "Ash")):
        _fill(
            client,
            kompas,
            [{"question_id": ids[0], "answer_int": given}, {"question_id": ids[1], "answer_int": 5}],
            name,
        )
    reply = _fill(
        client,
        kompas,
        [{"question_id": ids[0], "answer_int": 1}, {"question_id": ids[1], "answer_int": 5}],
        "Robin",
    )
    assert reply.status_code == 201, reply.text
    mine = reply.json()

    x_axis = next(row for row in mine["axes"] if row["axis"]["axis"] == "x")
    assert x_axis["axis"]["name"] == "Economie"
    assert x_axis["ci_low"] < x_axis["average"] < x_axis["ci_high"]
    # And it is the room, not the reader: they sit at -1 and the mean
    # does not.
    assert mine["x"] == -1.0
    assert x_axis["average"] > -1.0


def test_the_csv_rows_carry_the_coordinates(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    ids = [q["id"] for q in kompas["questions"]]
    _fill(client, kompas, [{"question_id": ids[0], "answer_int": 5}, {"question_id": ids[1], "answer_int": 1}])
    rows = client.get(f"/api/v1/compasses/{kompas['id']}/submissions", headers=organiser_headers).json()
    assert (rows[0]["x"], rows[0]["y"]) == (1.0, -1.0)


# --- the refusals ----------------------------------------------------


def test_a_kind_a_kompas_cannot_point_is_refused(client, organiser_headers) -> None:
    r = _create(client, organiser_headers, [{"kind": "text", "prompt": "Waarom?"}])
    assert r.status_code == 400
    assert "statements and multiple-choice" in r.json()["detail"]


def test_a_statement_without_a_side_is_refused(client, organiser_headers) -> None:
    r = _create(client, organiser_headers, [{"kind": "rating", "prompt": "Meer huizen"}])
    assert r.status_code == 400
    assert "Question 1" in r.json()["detail"]
    assert "a 5" in r.json()["detail"]


def test_an_option_without_a_side_is_refused(client, organiser_headers) -> None:
    r = _create(
        client,
        organiser_headers,
        [{"kind": "single_choice", "prompt": "Waarheen?", "options": ["A", "B"], "option_poles": ["x_low"]}],
    )
    assert r.status_code == 400
    assert "every answer" in r.json()["detail"]


def test_an_axis_no_question_touches_is_refused(client, organiser_headers) -> None:
    """Any of the four sides may go unused, which is the organiser's
    choice. An axis nothing touches is not a choice."""
    r = _create(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "x_low")])
    assert r.status_code == 400
    assert "Cultuur" in r.json()["detail"]


def test_an_unnamed_side_is_refused(client, organiser_headers) -> None:
    axes = [dict(AXES[0]), {**AXES[1], "high_name": ""}]
    r = _create(client, organiser_headers, [_statement("Een", "x_high")], axes=axes)
    # Empty strings fail the schema's own min_length before the service
    # ever sees them, which is the same refusal one layer earlier.
    assert r.status_code in (400, 422)


def test_a_kompas_with_nothing_to_answer_is_refused(client, organiser_headers) -> None:
    """There is no empty draft. A kompas with no questions is a public
    page whose only button does nothing, so the save is refused rather
    than published, and the message says what to do about it."""
    r = _create(client, organiser_headers, [], axes=[])
    assert r.status_code == 400, r.text
    assert "at least one question" in r.json()["detail"]


def test_a_kompas_is_not_reachable_through_the_forms_urls(client, organiser_headers) -> None:
    kompas = _compass(client, organiser_headers, [_statement("Een", "x_high"), _statement("Twee", "y_high")])
    assert client.get(f"/api/v1/forms/{kompas['id']}", headers=organiser_headers).status_code == 404
    assert client.get(f"/api/v1/quizzes/by-slug/{kompas['slug']}").status_code == 410
    assert [f["id"] for f in client.get("/api/v1/forms", headers=organiser_headers).json()] == []
