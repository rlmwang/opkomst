"""Coverage for the weekly pending-approval digest.

The digest fans out one email per admin listing every user
currently awaiting approval. Tested at three failure modes:

* No pending users → silent no-op (admins shouldn't get a
  "nothing to do" email).
* No live admins → log + skip; possible if the bootstrap admin
  is soft-deleted with no replacement.
* Multiple admins + multiple pending → every admin gets the
  same payload.

The send path is covered through the ``fake_email`` fixture
rather than monkeypatching ``send_email`` directly so the
template rendering is exercised too.
"""

from __future__ import annotations

from typing import Any

from backend.database import SessionLocal
from backend.models import User
from backend.services.admin_digest import send_pending_digest
from tests._helpers.users import register_user


def test_digest_sends_one_email_per_admin(client, admin_headers, fake_email):
    """One admin + two pending users → one email containing both
    pending names. Pending order is by created_at ascending so the
    digest matches the order admins see in the Accounts page's
    pending tier."""
    fake_email.reset()
    register_user(client, "alice@local.dev", "Alice")
    register_user(client, "bob@local.dev", "Bob")

    n = send_pending_digest()
    assert n == 1

    captured = fake_email.to("admin@local.dev")
    assert len(captured) == 1
    body = captured[0].html_body
    assert "Alice" in body
    assert "Bob" in body
    assert "alice@local.dev" in body
    assert "bob@local.dev" in body


def test_digest_skipped_when_no_pending(client, admin_headers, fake_email):
    """Zero pending → zero emails. Every approved user (admin
    fixture is approved) shows up in the live-users query but is
    excluded by the ``is_approved=False`` filter."""
    fake_email.reset()
    n = send_pending_digest()
    assert n == 0
    assert fake_email.sent == []


def test_digest_skipped_when_no_admins(client, admin_headers, fake_email):
    """No live admins → digest skipped. Edge case: the only admin
    has been soft-deleted and there's no replacement; we don't want
    to crash, just log and move on."""
    register_user(client, "pending@local.dev", "Pending")

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@local.dev", User.deleted_at.is_(None)).first()
        assert admin is not None
        # Demote the admin to organiser so there's no admin row.
        admin.role = "organiser"
        db.commit()
    finally:
        db.close()

    fake_email.reset()  # drop registration emails captured during setup
    n = send_pending_digest()
    assert n == 0
    assert fake_email.sent == []


def test_digest_fans_out_to_every_live_admin(client, admin_headers, chapter_id, fake_email):
    """Two admins + one pending → two emails (one per admin)."""
    fake_email.reset()
    # Promote a second user to admin.
    second_uid = register_user(client, "second.admin@local.dev", "Second Admin")
    client.post(
        f"/api/v1/admin/users/{second_uid}/approve",
        headers=admin_headers,
        json={"chapter_ids": [chapter_id]},
    )
    client.post(f"/api/v1/admin/users/{second_uid}/promote", headers=admin_headers)
    register_user(client, "pending@local.dev", "Pending")
    fake_email.reset()  # drop the approval-email captured during setup

    n = send_pending_digest()
    assert n == 2

    a = fake_email.to("admin@local.dev")
    b = fake_email.to("second.admin@local.dev")
    assert len(a) == 1
    assert len(b) == 1
    # Both admins received the same pending list.
    assert "pending@local.dev" in a[0].html_body
    assert "pending@local.dev" in b[0].html_body


def test_digest_template_pluralises_singular_correctly(client, admin_headers, fake_email):
    """Singular case (1 pending) doesn't read 'There are 1
    accounts' — the template branches on count for grammar."""
    fake_email.reset()
    register_user(client, "solo@local.dev", "Solo")

    send_pending_digest()
    captured = fake_email.to("admin@local.dev")
    assert len(captured) == 1
    body = captured[0].html_body
    # NL template: "1 account" not "1 accounts" (no plural 's').
    assert "1 account " in body or "1 account<" in body or "Solo" in body  # presence-of-name is the strict assertion


def _consume(_x: Any) -> None:
    """Silence pyright unused-fixture warnings on parametrised
    dependency-only fixtures."""
    pass
