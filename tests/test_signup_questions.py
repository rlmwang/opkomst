"""The sign-up form's two questions, each with its own switch.

"Hoe heb je ons gevonden?" and "Ik kan helpen met" are optional. A
switched-off question is not asked: its options never reach the public
page, and an answer to it is refused rather than recorded.
"""

from typing import Any

from backend.models import Event

_BASE: dict[str, Any] = {
    "name_nl": "Demo",
    "topic_nl": None,
    "location": "Adam",
    "starts_on": "2026-09-01",
    "start_time": "18:00:00",
    "end_time": "20:00:00",
    "feedback_enabled": True,
    "reminder_enabled": False,
    "locale": "nl",
}


def _chapter(client: Any, headers: dict[str, str]) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _labels(options: Any) -> Any:
    """Option lists are rows on the wire; the tests write plain labels."""
    if isinstance(options, list):
        return [{"label": o} if isinstance(o, str) else o for o in options]
    return options


def _create(client: Any, headers: dict[str, str], **overrides: Any):
    for key in ("source_options", "help_options"):
        if key in overrides:
            overrides[key] = _labels(overrides[key])
    payload = {**_BASE, "chapter_id": _chapter(client, headers), **overrides}
    return client.post("/api/v1/event", headers=headers, json=payload)


def _public(client: Any, event: dict[str, Any]) -> dict[str, Any]:
    """What the public sign-up page is handed for this event."""
    r = client.get(f"/api/v1/event/by-slug/{event['next_slug']}")
    assert r.status_code == 200, r.text
    return r.json()


def test_an_asked_question_needs_something_to_offer(client, organiser_headers) -> None:
    """A switched-on question with no options would render as an empty
    dropdown or an empty checklist."""
    assert _create(client, organiser_headers, source_options=[], source_enabled=True).status_code == 422
    assert (
        _create(
            client,
            organiser_headers,
            source_options=["Flyer"],
            help_options=[],
            help_enabled=True,
        ).status_code
        == 422
    )


def test_a_switched_off_question_needs_nothing(client, organiser_headers) -> None:
    r = _create(client, organiser_headers, source_options=[], source_enabled=False)
    assert r.status_code == 201, r.text
    assert r.json()["source_enabled"] is False


def test_the_options_survive_being_switched_off(client, organiser_headers, db) -> None:
    """Switching a question back on has to bring the organiser's own
    list back, not an empty one."""
    created = _create(
        client,
        organiser_headers,
        source_options=["Flyer", "Vriend"],
        help_options=["Opbouwen"],
        help_enabled=True,
    ).json()

    off = client.put(
        f"/api/v1/event/{created['id']}",
        headers=organiser_headers,
        json={
            **_BASE,
            "chapter_id": created["chapter_id"],
            **{
                "source_options": [{"label": "Flyer"}, {"label": "Vriend"}],
                "source_enabled": False,
                "help_options": [{"label": "Opbouwen"}],
                "help_enabled": False,
                "period_weeks": 1,
                "cycle_slots": [],
                "span_weeks": None,
                "horizon_days": 90,
                "listed": True,
            },
        },
    )
    assert off.status_code == 200, off.text
    row = db.query(Event).filter(Event.id == created["id"]).one()
    assert [o.label for o in row.source_options] == ["Flyer", "Vriend"]
    assert [o.label for o in row.help_options] == ["Opbouwen"]


def test_the_public_page_is_never_told_about_a_question_it_isnt_asking(client, organiser_headers) -> None:
    created = _create(
        client,
        organiser_headers,
        source_options=["Flyer"],
        source_enabled=False,
        help_options=["Opbouwen"],
        help_enabled=True,
    ).json()
    page = _public(client, created)
    assert page["source_options"] == []
    assert [o["label"] for o in page["help_options"]] == ["Opbouwen"]


def test_an_answer_to_a_switched_off_question_is_refused(client, organiser_headers) -> None:
    """A stale page or a hand-made request. There is no question, so
    there is nothing to record."""
    created = _create(
        client,
        organiser_headers,
        source_options=["Flyer"],
        source_enabled=False,
        help_options=["Opbouwen"],
        help_enabled=False,
    ).json()
    slug = created["next_slug"]

    refused_source = client.post(
        f"/api/v1/event/by-slug/{slug}/signups",
        json={"display_name": "Aisha", "party_size": 1, "source_choice": "made-up", "all_upcoming": True},
    )
    assert refused_source.status_code == 400

    refused_help = client.post(
        f"/api/v1/event/by-slug/{slug}/signups",
        json={"display_name": "Aisha", "party_size": 1, "help_choices": ["Opbouwen"], "all_upcoming": True},
    )
    assert refused_help.status_code == 400

    # Without an answer to either, the sign-up goes through.
    ok = client.post(
        f"/api/v1/event/by-slug/{slug}/signups",
        json={"display_name": "Aisha", "party_size": 1, "all_upcoming": True},
    )
    assert ok.status_code == 201, ok.text
