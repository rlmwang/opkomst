"""The four ``POST /api/v1/start/{kind}`` endpoints.

A visitor with no account fills in a create form at the root, gives an
address, and gets back a public link that already works. Covered here:
the account is created on a first-time address and reused on a known
one, the response is the same either way, the entity really belongs to
that account, and a sign-in link is mailed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.models import Datepoll, Event, Form, LoginToken, Occurrence, Roster, Tenant, User


def _event_body() -> dict[str, Any]:
    soon = date.today() + timedelta(days=14)
    return {
        "name_nl": "Buurtborrel",
        "name_en": None,
        "topic_nl": None,
        "topic_en": None,
        "location": "Utrecht",
        "latitude": None,
        "longitude": None,
        "starts_on": soon.isoformat(),
        "start_time": "20:00:00",
        "end_time": "22:00:00",
        "period_weeks": 1,
        "cycle_slots": [],
        "span_weeks": None,
        "horizon_days": 90,
        "source_options": ["Van een vriend"],
        "help_options": [],
        "feedback_enabled": False,
        "reminder_enabled": False,
        "listed": True,
        "locale": "nl",
        "image_artist_instagram": None,
    }


def _form_body() -> dict[str, Any]:
    return {
        "name_nl": "Wat vind je ervan",
        "name_en": None,
        "description_nl": None,
        "description_en": None,
        "image_artist_instagram": None,
        "locale": "nl",
        "questions": [
            {
                "id": None,
                "kind": "text",
                "prompt": "Waarom?",
                "required": False,
                "options": [],
                "low_label": None,
                "high_label": None,
            }
        ],
    }


def _datepoll_body() -> dict[str, Any]:
    soon = date.today() + timedelta(days=7)
    return {
        "name_nl": "Wanneer kan iedereen",
        "name_en": None,
        "description_nl": None,
        "description_en": None,
        "location": None,
        "latitude": None,
        "longitude": None,
        "image_artist_instagram": None,
        "locale": "nl",
        "slots": [{"on_date": soon.isoformat()}],
    }


def _roster_body() -> dict[str, Any]:
    return {
        "name_nl": "Corvee",
        "name_en": None,
        "description_nl": None,
        "description_en": None,
        "image_artist_instagram": None,
        "locale": "nl",
        "location": None,
        "latitude": None,
        "longitude": None,
        "period_weeks": 1,
        "starts_on": date.today().isoformat(),
        "ends_on": None,
        "reminder_enabled": False,
        "reminder_days_before": 1,
        "commit_horizon_days": 28,
        "chores": [
            {"id": None, "name": "Afwas", "description": None, "cycle_slots": [0], "people_per_shift": 1, "emoji": None}
        ],
    }


def _personal_user(db, email: str) -> User | None:
    return (
        db.query(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .filter(User.email == email, Tenant.kind == "personal", User.deleted_at.is_(None))
        .first()
    )


def test_new_address_gets_a_tenant_a_user_and_the_entity(client, db) -> None:
    """The whole account is made on the way through: a personal tenant,
    its one approved organiser, and the event they asked for."""
    resp = client.post("/api/v1/start/events", json={"email": "Nieuw@Example.org", "event": _event_body()})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["public_url"].endswith(f"/e/{body['slug']}")

    # Stored lowercase, so the account is the address however it was
    # typed. Same rule as every other door.
    user = _personal_user(db, "nieuw@example.org")
    assert user is not None
    assert user.role == "organiser"
    assert user.is_approved is True
    assert user.tenant.kind == "personal"
    # The slug names the row but never appears in a URL, so it is a
    # generated id rather than anything derived from the address.
    assert user.tenant.slug != "nieuw@example.org"

    # ``/e/{slug}`` is per occurrence, so the link names the first
    # session rather than the event, and resolves the moment it is
    # shared.
    assert client.get(f"/api/v1/events/by-slug/{body['slug']}").status_code == 200
    occurrence = db.query(Occurrence).filter(Occurrence.slug == body["slug"]).one()
    event = db.query(Event).filter(Event.id == occurrence.event_id).one()
    assert event.tenant_id == user.tenant_id
    assert event.created_by == user.id
    # A personal tenant has no chapters, so nothing is assigned to one.
    assert event.chapter_id is None


def test_known_address_writes_into_the_existing_account(client, db) -> None:
    """Second time round nothing is created but the entity: the address
    already is an account."""
    first = client.post("/api/v1/start/events", json={"email": "vaste@example.org", "event": _event_body()})
    assert first.status_code == 201
    user = _personal_user(db, "vaste@example.org")
    assert user is not None
    tenant_id, user_id = user.tenant_id, user.id

    second = client.post("/api/v1/start/forms", json={"email": "vaste@example.org", "form": _form_body()})
    assert second.status_code == 201

    assert db.query(Tenant).filter(Tenant.kind == "personal").count() == 1
    assert db.query(User).filter(User.id == user_id).count() == 1
    form = db.query(Form).filter(Form.slug == second.json()["slug"]).one()
    assert form.tenant_id == tenant_id


def test_response_does_not_say_whether_the_account_existed(client) -> None:
    """Same shape, same status, same fields. Whether an address already
    has an account is not something a stranger gets to probe."""
    new = client.post("/api/v1/start/events", json={"email": "a@example.org", "event": _event_body()})
    again = client.post("/api/v1/start/events", json={"email": "a@example.org", "event": _event_body()})
    assert new.status_code == again.status_code == 201
    assert sorted(new.json()) == sorted(again.json())


def test_a_sign_in_link_is_minted_for_the_account(client, db) -> None:
    """The mail is the disclosure: whoever owns the address learns that
    something landed in their account, and gets the way in."""
    client.post("/api/v1/start/events", json={"email": "post@example.org", "event": _event_body()})
    user = _personal_user(db, "post@example.org")
    assert user is not None
    assert db.query(LoginToken).filter(LoginToken.user_id == user.id).count() == 1


def test_the_mail_is_written_in_the_language_the_form_was(db) -> None:
    """The visitor filled the form in one language; the mail about it
    arrives in the same one. Both templates have to render for every
    kind, since each names the kind in its own words."""
    from backend.services.mail import render

    for kind, nl_noun, en_noun in [
        ("event", "evenement", "event"),
        ("form", "vragenlijst", "form"),
        ("datepoll", "datumplanner", "date poll"),
        ("roster", "takenrooster", "chore roster"),
    ]:
        context = {
            "account": "iemand@example.org",
            "kind": kind,
            "name": "Iets",
            "public_url": "https://opkomst.nu/e/abcd1234",
            "login_url": "https://opkomst.nu/auth/redeem?token=x",
        }
        nl_subject, nl_body = render("started.html", context, locale="nl")
        en_subject, en_body = render("started.html", context, locale="en")
        assert nl_noun in nl_subject.lower()
        assert en_noun in en_subject.lower()
        # The account is named in both, which is the whole disclosure.
        assert "iemand@example.org" in nl_body
        assert "iemand@example.org" in en_body


def test_every_kind_has_a_door(client, db) -> None:
    """Forms, datepolls and rosters take the same route as events, each
    landing on its own public prefix."""
    cases = [
        ("forms", "form", _form_body(), "f", Form),
        ("datepolls", "datepoll", _datepoll_body(), "d", Datepoll),
        ("chores", "roster", _roster_body(), "c", Roster),
    ]
    for path, key, body, prefix, model in cases:
        resp = client.post(f"/api/v1/start/{path}", json={"email": f"{path}@example.org", key: body})
        assert resp.status_code == 201, resp.text
        out = resp.json()
        assert f"/{prefix}/{out['slug']}" in out["public_url"]
        row = db.query(model).filter(model.slug == out["slug"]).one()
        assert row.chapter_id is None


def test_a_chapter_id_is_refused(client, db, chapter_id) -> None:
    """The account this creates has no chapters, and the chapter ids it
    could name are somebody else's. Without this the body could put an
    anonymous event onto an organisation's public agenda, which reads
    rows by chapter id."""
    before = db.query(Event).count()
    body = {"email": "sluiper@example.org", "event": {**_event_body(), "chapter_id": chapter_id}}
    resp = client.post("/api/v1/start/events", json=body)
    assert resp.status_code == 422
    assert db.query(Event).count() == before


def test_a_bad_address_is_refused_before_anything_is_written(client, db) -> None:
    before = db.query(Tenant).count()
    resp = client.post("/api/v1/start/events", json={"email": "not-an-address", "event": _event_body()})
    assert resp.status_code == 422
    assert db.query(Tenant).count() == before
