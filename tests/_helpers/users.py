"""Auth flow helpers for tests.

Single entry point for the new flow: a test-side helper that runs
the full ``/login-link`` → ``/complete-registration`` round-trip
and returns the freshly-created user's ``id``. Bootstrap admin
gets the same path — the carve-out triggers on the first
completion when the email matches ``BOOTSTRAP_ADMIN_EMAIL``.

Tests that don't care about exercising the real flow can use
``register_user`` and treat it as a one-liner; tests that *do*
care call the public endpoints directly.
"""

from typing import Any

from backend.database import SessionLocal
from backend.models import RegistrationToken, User


def register_user(client: Any, email: str, name: str = "X") -> str:
    """Run the magic-link sign-up flow end-to-end and return the
    newly-created user's id. Asserts the round-trip succeeded so a
    test failure here points at a real auth regression rather than
    a downstream symptom."""
    r = client.post("/api/v1/auth/login-link", json={"email": email})
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        row = (
            db.query(RegistrationToken)
            .filter(RegistrationToken.email == email)
            .order_by(RegistrationToken.created_at.desc())
            .first()
        )
        assert row is not None, f"no RegistrationToken minted for {email}"
        raw = row.token
    finally:
        db.close()

    r = client.post(
        "/api/v1/auth/complete-registration",
        json={"token": raw, "name": name},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email, User.deleted_at.is_(None)).first()
        assert user is not None
        return user.id
    finally:
        db.close()
