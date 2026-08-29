"""Chore email-state contract (§6).

The volunteer address is retained (encrypted) only while reminders are
on; it's used once for the welcome link otherwise and never stored.
Invariant asserted throughout: ``email_reminders`` False ⇒
``encrypted_email`` IS NULL.

Parallels ``test_email_state_machine.py`` (which covers the *events*
EmailDispatch wipe rule — a separate table/contract).
"""

from __future__ import annotations

from typing import Any

from backend.models import Enrollment, Volunteer


def _chapter_id(client: Any, headers: Any) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["chapters"][0]["id"]


def _roster(client: Any, headers: Any) -> dict[str, Any]:
    r = client.post(
        "/api/v1/chore",
        headers=headers,
        json={
            "chapter_id": _chapter_id(client, headers),
            "name_nl": "R",
            "starts_on": "2026-01-05",
            "chores": [{"name": "Bins", "cycle_slots": [2]}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _volunteer(db: Any, roster_id: str) -> Volunteer | None:
    # Drop what this session has cached and read the request's writes
    # again. It used to be ``rollback()``, back when the request
    # committed for real; inside the test transaction that would throw
    # the request's work away with it.
    db.expire_all()
    return db.query(Volunteer).filter(Volunteer.roster_id == roster_id).first()


def _enroll(client: Any, slug: str, **body: Any) -> str:
    r = client.post(f"/api/v1/chore/by-slug/{slug}/enroll", json=body)
    assert r.status_code == 200, r.text
    return r.json()["edit_token"]


def test_enroll_with_reminders_retains_ciphertext(client, organiser_headers, db):
    roster = _roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _enroll(client, roster["slug"], display_name="Ada", email="ada@local.dev", email_reminders=True, chore_ids=[cid])
    v = _volunteer(db, roster["id"])
    assert v is not None
    assert v.encrypted_email is not None
    assert v.email_reminders is True


def test_enroll_email_without_reminders_is_not_retained(client, organiser_headers, db):
    # Email given but reminders off → welcome sent, address not stored.
    roster = _roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    _enroll(client, roster["slug"], display_name="Ada", email="ada@local.dev", email_reminders=False, chore_ids=[cid])
    v = _volunteer(db, roster["id"])
    assert v is not None
    assert v.email_reminders is False
    assert v.encrypted_email is None  # invariant


def test_mute_wipes_ciphertext_but_keeps_enrolment(client, organiser_headers, db):
    roster = _roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    token = _enroll(
        client, roster["slug"], display_name="Ada", email="ada@local.dev", email_reminders=True, chore_ids=[cid]
    )
    # Mute: reminders off, keep the chore pick.
    r = client.put(
        f"/api/v1/chore/by-token/{token}",
        json={"display_name": "Ada", "chore_ids": [cid], "email_reminders": False},
    )
    assert r.status_code == 200, r.text
    v = _volunteer(db, roster["id"])
    assert v is not None
    assert v.email_reminders is False
    assert v.encrypted_email is None  # invariant: muted ⇒ wiped
    # Enrolment survives the mute.
    kept = db.query(Enrollment).filter(Enrollment.volunteer_id == v.id).count()
    assert kept == 1


def test_leave_removes_the_row(client, organiser_headers, db):
    roster = _roster(client, organiser_headers)
    cid = roster["chores"][0]["id"]
    token = _enroll(
        client, roster["slug"], display_name="Ada", email="ada@local.dev", email_reminders=True, chore_ids=[cid]
    )
    assert client.post(f"/api/v1/chore/by-token/{token}/leave").status_code == 204
    assert _volunteer(db, roster["id"]) is None
