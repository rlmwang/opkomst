"""What a personal account is, and what it cannot reach.

A personal tenant holds one person and no chapters. That shapes three
things, each checked here: the surfaces it is refused (admin, chapters,
WhatsApp), the scope rule that would otherwise hide its own rows (they
have no ``chapter_id`` to match), and the ceilings that exist because
the root hands an account to anyone who types an address.

An organisation is the control in every one of these: none of the
ceilings apply to it, and none of the refusals do either.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from backend.auth import create_token
from backend.models import Event, Form, Tenant, User
from backend.services import access, limits
from backend.services import tenants as tenants_svc
from tests._helpers.events import public_option_ids


@pytest.fixture()
def personal(db, tenant_id) -> tuple[Tenant, User, dict[str, str]]:
    """A personal account: its tenant, its one user, and the headers
    that sign requests as them."""
    user = tenants_svc.create_personal(db, "solo@example.org")
    db.commit()
    db.refresh(user)
    # ``create_personal`` binds its own tenant for the duration of the
    # write and restores it after, which is what keeps the rest of a
    # test's direct-session inserts in the organisation they belong to.
    # Requests bind their own tenant from the token.
    return user.tenant, user, {"Authorization": f"Bearer {create_token(user)}"}


def _event_payload(**over: Any) -> dict[str, Any]:
    soon = date.today() + timedelta(days=10)
    body = {
        "name_nl": "Borrel",
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
        "source_options": [{"label": "Van een vriend"}],
        "source_enabled": True,
        "help_options": [],
        "feedback_enabled": False,
        "reminder_enabled": False,
        "listed": True,
        "locale": "nl",
        "image_artist_instagram": None,
    }
    body.update(over)
    return body


# ---- The surfaces it doesn't have -------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/v1/admin/users"),
        ("get", "/api/v1/admin/users/pending-count"),
        ("get", "/api/v1/chapters"),
        ("post", "/api/v1/chapters"),
        ("get", "/api/v1/settings"),
        ("get", "/api/v1/whatsapp/status"),
    ],
)
def test_organisation_only_routes_are_not_there(client, personal, method, path) -> None:
    """404, not 403: a personal account isn't being kept out of a room,
    the room doesn't exist for it, and the difference is not something
    the surface should advertise."""
    _, _, headers = personal
    resp = getattr(client, method)(path, headers=headers, **({"json": {"name": "X"}} if method == "post" else {}))
    assert resp.status_code == 404


def test_an_organisation_still_reaches_them(client, admin_headers) -> None:
    """The control: the same routes answer normally for an
    organisation's admin."""
    assert client.get("/api/v1/admin/users", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/chapters", headers=admin_headers).status_code == 200


def test_me_says_which_kind_of_account_this_is(client, personal) -> None:
    """The frontend hides what doesn't exist off this one field, so it
    has to be on ``/me``."""
    _, _, headers = personal
    body = client.get("/api/v1/auth/me", headers=headers).json()
    assert body["tenant_kind"] == "personal"
    assert body["participant_cap"] == limits.MAX_PARTICIPANTS
    assert body["chapters"] == []


def test_an_organisations_me_has_no_ceiling(client, admin_headers) -> None:
    body = client.get("/api/v1/auth/me", headers=admin_headers).json()
    assert body["tenant_kind"] == "organisation"
    assert body["participant_cap"] is None


# ---- Chapters -----------------------------------------------------


def test_creating_something_needs_no_chapter(client, personal, db) -> None:
    _, user, headers = personal
    resp = client.post("/api/v1/event", json=_event_payload(chapter_id=None), headers=headers)
    assert resp.status_code == 201, resp.text
    event = db.query(Event).filter(Event.id == resp.json()["id"]).one()
    assert event.chapter_id is None
    assert event.tenant_id == user.tenant_id


def test_assigning_a_chapter_is_a_malformed_request(client, personal, chapter_id) -> None:
    """422, not 403: there is no chapter this account could have meant,
    so the body is wrong rather than the caller unauthorised."""
    _, _, headers = personal
    resp = client.post("/api/v1/event", json=_event_payload(chapter_id=chapter_id), headers=headers)
    assert resp.status_code == 422


def test_an_organisation_must_still_pick_one(client, organiser_headers) -> None:
    resp = client.post("/api/v1/event", json=_event_payload(chapter_id=None), headers=organiser_headers)
    assert resp.status_code == 422


def test_it_sees_its_own_rows_despite_having_no_chapters(client, personal, db) -> None:
    """The rule that would otherwise break: the chapter set narrows an
    organisation's scope, and for a personal account the tenant is the
    whole of it."""
    _, user, headers = personal
    created = client.post("/api/v1/event", json=_event_payload(), headers=headers)
    assert created.status_code == 201
    listed = client.get("/api/v1/event", headers=headers)
    assert [e["id"] for e in listed.json()["items"]] == [created.json()["id"]]
    assert access.is_personal(db, user) is True


def test_it_cannot_see_another_tenants_rows(client, personal, db, chapter_id, admin_headers) -> None:
    """The tenant predicate is in the scope filter itself, so a personal
    account's empty chapter set never widens into everyone's rows."""
    theirs = client.post("/api/v1/event", json=_event_payload(chapter_id=chapter_id), headers=admin_headers)
    assert theirs.status_code == 201, theirs.text
    _, _, headers = personal
    assert client.get("/api/v1/event", headers=headers).json()["items"] == []
    assert client.get(f"/api/v1/event/{theirs.json()['id']}", headers=headers).status_code == 404


# ---- The ceilings -------------------------------------------------


def test_active_entities_are_capped_and_archiving_makes_room(client, personal, db, monkeypatch) -> None:
    """The count is of live rows: archiving is how you free a slot."""
    monkeypatch.setattr(limits, "MAX_ACTIVE_PER_KIND", 2)
    _, _, headers = personal
    first = client.post("/api/v1/event", json=_event_payload(), headers=headers)
    client.post("/api/v1/event", json=_event_payload(), headers=headers)
    full = client.post("/api/v1/event", json=_event_payload(), headers=headers)
    assert full.status_code == 409
    assert "Archive" in full.json()["detail"]

    assert client.post(f"/api/v1/event/{first.json()['id']}/archive", headers=headers).status_code in (200, 204)
    assert client.post("/api/v1/event", json=_event_payload(), headers=headers).status_code == 201


def test_an_organisation_has_no_entity_ceiling(client, organiser_headers, chapter_id, monkeypatch) -> None:
    monkeypatch.setattr(limits, "MAX_ACTIVE_PER_KIND", 1)
    body = _event_payload(chapter_id=chapter_id)
    assert client.post("/api/v1/event", json=body, headers=organiser_headers).status_code == 201
    assert client.post("/api/v1/event", json=body, headers=organiser_headers).status_code == 201


def test_a_party_counts_for_everyone_it_brings(client, personal, db, monkeypatch) -> None:
    """The cap is on people, not bookings, so a party of four takes four
    of the places."""
    monkeypatch.setattr(limits, "MAX_PARTICIPANTS", 5)
    _, _, headers = personal
    created = client.post("/api/v1/event", json=_event_payload(), headers=headers)
    slug = created.json()["next_slug"]

    signup = {
        "display_name": "Aisha",
        "party_size": 4,
        **public_option_ids(client, slug, source="Van een vriend"),
        "help_choices": [],
        "all_upcoming": True,
    }
    assert client.post(f"/api/v1/event/by-slug/{slug}/signups", json=signup).status_code == 201
    # One more of four would make eight, past the five places.
    refused = client.post(f"/api/v1/event/by-slug/{slug}/signups", json=signup)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This is full. No more places are available."


def test_an_organisations_event_has_no_participant_ceiling(client, organiser_headers, chapter_id, monkeypatch) -> None:
    monkeypatch.setattr(limits, "MAX_PARTICIPANTS", 1)
    created = client.post("/api/v1/event", json=_event_payload(chapter_id=chapter_id), headers=organiser_headers)
    slug = created.json()["next_slug"]
    signup = {
        "display_name": "Bo",
        "party_size": 3,
        **public_option_ids(client, slug, source="Van een vriend"),
        "help_choices": [],
        "all_upcoming": True,
    }
    assert client.post(f"/api/v1/event/by-slug/{slug}/signups", json=signup).status_code == 201
    assert client.post(f"/api/v1/event/by-slug/{slug}/signups", json=signup).status_code == 201


def test_the_mail_budget_only_binds_a_personal_account(db, personal, tenant_id) -> None:
    from backend.models import Tenant as TenantModel

    tenant, _, _ = personal
    assert limits.mail_budget_remaining(db, tenant) == limits.MAX_MAIL_PER_DAY
    organisation = db.query(TenantModel).filter(TenantModel.id == tenant_id).one()
    assert limits.mail_budget_remaining(db, organisation) is None
    assert limits.has_mail_budget(db, organisation, wanted=10_000) is True


# ---- The brand it wears -------------------------------------------


def test_a_personal_tenant_wears_the_house_brand(db, personal) -> None:
    """Its slug is a generated id with no folder under ``brands/``. Every
    surface that renders one asks the tenant, so nothing tries to read
    ``brands/{nanoid}/brand.json`` and blow up: that would take out the
    public page the start flow exists to produce, and permanently fail
    the mail (a failed dispatch nulls the address it needed)."""
    from backend.services import brand as brand_svc

    tenant, _, _ = personal
    assert tenant.brand_slug == brand_svc.HOUSE_BRAND
    # Reads the manifest, so it raises if the folder isn't there.
    assert brand_svc.payload(tenant.brand_slug)["slug"] == brand_svc.HOUSE_BRAND


def test_an_organisation_wears_its_own(db, tenant_id) -> None:
    from backend.models import Tenant as TenantModel

    organisation = db.query(TenantModel).filter(TenantModel.id == tenant_id).one()
    assert organisation.brand_slug == organisation.slug


def test_the_public_page_of_a_personal_entity_renders(client, personal) -> None:
    """End to end over the start flow's own output: the link it hands
    back has to open."""
    started = client.post(
        "/api/v1/start/event",
        json={"email": "opener@example.org", "event": _event_payload()},
    )
    assert started.status_code == 201, started.text
    page = client.get(f"/e/{started.json()['slug']}")
    # Without a frontend build the SPA routes aren't mounted at all; the
    # point of the check is that resolving the brand doesn't raise.
    assert page.status_code in (200, 404)


# ---- The account itself -------------------------------------------


def test_a_personal_slug_can_never_shadow_a_page(db) -> None:
    """The root's own paths and the organisation slugs are one
    namespace, so a generated slug must not land on one of them."""
    from backend.services.slug import RESERVED_SLUGS

    for _ in range(50):
        user = tenants_svc.create_personal(db, f"x{_}@example.org")
        db.flush()
        assert user.tenant.slug not in RESERVED_SLUGS


def test_two_addresses_are_two_accounts(db) -> None:
    a = tenants_svc.create_personal(db, "a@example.org")
    b = tenants_svc.create_personal(db, "b@example.org")
    db.flush()
    assert a.tenant_id != b.tenant_id
    assert a.tenant.slug != b.tenant.slug


def test_a_personal_user_is_approved_on_the_spot(db) -> None:
    """There is nobody to approve them: the tenant is them."""
    user = tenants_svc.create_personal(db, "self@example.org")
    db.flush()
    assert user.is_approved is True
    assert user.role == "organiser"


def test_a_form_lands_in_the_account_with_no_chapter(client, personal, db) -> None:
    _, user, headers = personal
    body = {
        "chapter_id": None,
        "name_nl": "Vragen",
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
    resp = client.post("/api/v1/form", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    form = db.query(Form).filter(Form.id == resp.json()["id"]).one()
    assert form.chapter_id is None
    assert form.tenant_id == user.tenant_id
