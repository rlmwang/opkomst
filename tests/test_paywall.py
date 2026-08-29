"""The plan: who may make the app mail the people they collect.

Mail is the only thing that scales with participants, so it is the only
thing behind a plan (``docs/design-paywall.md``). Three things are
checked here: an account is born on the right plan, the write paths
refuse a mail toggle a free account may not have, and the worker sends
nothing for one anyway. The transactional mail an account needs to exist
at all is the control: it is never gated.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from _helpers.events import first_occurrence, make_event

from backend.auth import create_token
from backend.cli import _tenant_plan
from backend.database import SessionLocal
from backend.models import Chore, EmailChannel, EmailDispatch, Event, Roster, Tenant, User, Volunteer
from backend.services import mail_lifecycle
from backend.services import tenants as tenants_svc


@pytest.fixture()
def free(db, tenant_id) -> tuple[Tenant, User, dict[str, str]]:
    """A personal account, which is where a free account comes from."""
    user = tenants_svc.create_personal(db, "solo@example.org")
    db.commit()
    db.refresh(user)
    return user.tenant, user, {"Authorization": f"Bearer {create_token(user)}"}


def _pay(db, tenant: Tenant) -> None:
    tenant.plan = "paid"
    db.commit()


def _event_payload(**over: Any) -> dict[str, Any]:
    soon = date.today() + timedelta(days=10)
    body: dict[str, Any] = {
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
        "source_options": [],
        "source_enabled": False,
        "help_options": [],
        "feedback_enabled": False,
        "reminder_enabled": False,
        "listed": True,
        "locale": "nl",
        "chapter_id": None,
        "image_artist_instagram": None,
    }
    body.update(over)
    return body


def _roster_payload(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name_nl": "Corvee",
        "name_en": None,
        "description_nl": None,
        "description_en": None,
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
        "chapter_id": None,
        "image_artist_instagram": None,
        "chores": [
            {"id": None, "name": "Afwas", "description": None, "cycle_slots": [0], "people_per_shift": 1, "emoji": None}
        ],
    }
    body.update(over)
    return body


# ---- Which plan an account is born on -------------------------------


def test_an_organisation_is_born_paid(db, tenant_id) -> None:
    """It is in ``TENANTS`` because an operator put it there, which is
    the same decision as paying for it."""
    assert db.query(Tenant).filter(Tenant.id == tenant_id).one().is_paid


def test_a_personal_account_is_born_free(free) -> None:
    tenant, _, _ = free
    assert not tenant.is_paid


# ---- The write paths ------------------------------------------------


def test_a_free_account_cannot_create_an_event_that_mails(free, client) -> None:
    _, _, headers = free
    r = client.post("/api/v1/event", json=_event_payload(reminder_enabled=True), headers=headers)
    assert r.status_code == 422, r.text
    assert "paid plan" in r.json()["detail"]


def test_feedback_mail_is_gated_the_same_way(free, client) -> None:
    _, _, headers = free
    r = client.post("/api/v1/event", json=_event_payload(feedback_enabled=True), headers=headers)
    assert r.status_code == 422, r.text


def test_a_free_account_may_have_the_event_itself(free, client) -> None:
    """The gate is on the mail, not on the product: same event, no
    toggles, 201."""
    _, _, headers = free
    assert client.post("/api/v1/event", json=_event_payload(), headers=headers).status_code == 201


def test_switching_it_on_later_is_refused_too(free, client) -> None:
    _, _, headers = free
    created = client.post("/api/v1/event", json=_event_payload(), headers=headers).json()
    r = client.put(
        f"/api/v1/event/{created['id']}",
        json=_event_payload(reminder_enabled=True),
        headers=headers,
    )
    assert r.status_code == 422, r.text


def test_a_paid_account_may_switch_it_on(free, client, db) -> None:
    tenant, _, headers = free
    _pay(db, tenant)
    r = client.post("/api/v1/event", json=_event_payload(reminder_enabled=True), headers=headers)
    assert r.status_code == 201, r.text


def test_the_start_door_is_gated_too(client) -> None:
    """The anonymous door creates a personal account, which is free, so
    a payload asking for mail is refused there as well."""
    r = client.post(
        "/api/v1/start/event",
        json={"email": "anon@example.org", "event": _event_payload(reminder_enabled=True)},
    )
    assert r.status_code == 422, r.text


def test_a_free_account_cannot_create_a_roster_that_mails(free, client) -> None:
    _, _, headers = free
    r = client.post("/api/v1/chore", json=_roster_payload(reminder_enabled=True), headers=headers)
    assert r.status_code == 422, r.text


# ---- The public surfaces --------------------------------------------


def test_the_public_roster_says_whether_it_sends(free, client, db) -> None:
    """The enrol page asks for an address only when something will use
    it, the same rule the public event page follows."""
    _, _, headers = free
    created = client.post("/api/v1/chore", json=_roster_payload(), headers=headers).json()
    slug = db.query(Roster).filter(Roster.id == created["id"]).one().slug
    body = client.get(f"/api/v1/chore/by-slug/{slug}").json()
    assert body["reminder_enabled"] is False


def test_a_roster_that_sends_nothing_keeps_no_address(free, client, db) -> None:
    """A stale page that ticks the box anyway still leaves no ciphertext
    behind: the roster is not going to mail anyone."""
    _, _, headers = free
    created = client.post("/api/v1/chore", json=_roster_payload(), headers=headers).json()
    roster = db.query(Roster).filter(Roster.id == created["id"]).one()
    chore = db.query(Chore).filter(Chore.roster_id == roster.id).first()
    r = client.post(
        f"/api/v1/chore/by-slug/{roster.slug}/enroll",
        json={
            "display_name": "V",
            "email": "v@example.org",
            "email_reminders": True,
            "chore_ids": [chore.id],
        },
    )
    assert r.status_code == 200, r.text
    volunteer = db.query(Volunteer).filter(Volunteer.roster_id == roster.id).one()
    assert volunteer.encrypted_email is None
    assert volunteer.email_reminders is False


# ---- The worker -----------------------------------------------------


def test_the_worker_sends_nothing_for_a_free_account(db, tenant_id, fake_email) -> None:
    """The backstop. The toggles are refused on write and cleared on
    downgrade, so a pending row here means one raced the other."""
    event = make_event(db, starts_in=timedelta(hours=2), reminder_enabled=True, feedback_enabled=False)
    db.add(
        EmailDispatch(
            occurrence_id=first_occurrence(event).id,
            channel=EmailChannel.REMINDER,
            encrypted_email=_ciphertext(),
        )
    )
    db.commit()

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one()
    tenant.plan = "free"
    db.commit()

    assert mail_lifecycle.run_once(EmailChannel.REMINDER) == 1  # row seen
    assert fake_email.sent == []  # and skipped


def _ciphertext() -> bytes:
    from backend.services import encryption

    return encryption.encrypt("attendee@example.org")


# ---- Dropping a plan ------------------------------------------------


def test_dropping_to_free_clears_the_toggles_and_the_queue(free, client, db) -> None:
    """An account that may not mail its participants may not have the
    toggles on either, and the ciphertext queued behind them goes with
    them."""
    tenant, _, headers = free
    _pay(db, tenant)
    created = client.post(
        "/api/v1/event",
        json=_event_payload(reminder_enabled=True, feedback_enabled=True),
        headers=headers,
    ).json()
    slug = first_occurrence(db.query(Event).filter(Event.id == created["id"]).one()).slug
    r = client.post(
        f"/api/v1/event/by-slug/{slug}/signups",
        json={"display_name": "Alice", "party_size": 1, "email": "alice@example.org", "all_upcoming": True},
    )
    assert r.status_code == 201, r.text
    assert db.query(EmailDispatch).count() > 0

    assert _tenant_plan("solo@example.org", "free") == 0

    fresh = SessionLocal()
    try:
        event = fresh.query(Event).filter(Event.id == created["id"]).one()
        assert event.reminder_enabled is False
        assert event.feedback_enabled is False
        assert fresh.query(EmailDispatch).count() == 0
        assert fresh.query(Tenant).filter(Tenant.id == tenant.id).one().is_paid is False
    finally:
        fresh.close()


def test_an_organisation_is_not_the_commands_business(db, tenant_id) -> None:
    """Its plan follows ``TENANTS``, so there is nothing to set here."""
    assert _tenant_plan("rsp", "free") == 1
    assert db.query(Tenant).filter(Tenant.id == tenant_id).one().is_paid


# ---- What is never gated --------------------------------------------


def test_a_free_account_still_gets_its_sign_in_link(client, fake_email) -> None:
    """One send per request, bounded by the rate limiter, and the only
    way into the account. Gating it would gate the app."""
    r = client.post("/api/v1/auth/login-link", json={"email": "solo@example.org"})
    assert r.status_code == 200, r.text
    assert len(fake_email.sent) == 1


def test_the_start_door_still_mails_what_it_made(client, fake_email) -> None:
    r = client.post("/api/v1/start/event", json={"email": "anon@example.org", "event": _event_payload()})
    assert r.status_code == 201, r.text
    assert len(fake_email.sent) == 1
