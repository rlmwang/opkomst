"""Test fixtures.

A fresh sqlite-mem DB per test, seeded with two users (``admin`` /
``organiser``) and one chapter (``Amsterdam``) so individual tests
can focus on their behaviour rather than re-bootstrapping the world
every time.

Each test gets its own ``TestClient`` bound to that DB; module
imports are kept inside fixtures so the app's startup-time
``run_migrations`` / ``run_seed`` don't fight per-test setup.
"""

import os
import sys
import tempfile
from collections.abc import Iterator

import pytest

# A per-process tempfile DB. ``:memory:`` would be cleaner but
# SQLAlchemy's default pool gives each connection its own empty
# in-memory DB, breaking tests that share state across requests.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB}")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-real-use")
os.environ.setdefault("EMAIL_ENCRYPTION_KEY", "19zJgFa6AyDoFI90PVOcY3/A8xH/3qXGyJt/hAVlCOA=")
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:5173")
os.environ.setdefault("DISABLE_SCHEDULER", "1")
# Bootstrap email is read at module-import time in
# ``routers/auth.py``; setting it after imports would be a no-op.
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@local.dev")

# Repo root on sys.path so ``backend`` imports cleanly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture()
def db():
    """Per-test fresh DB. Drops all SCD2 chains between tests so
    state can't leak."""
    from backend.database import Base, SessionLocal, engine

    # In-memory sqlite — drop+create fresh for every test.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db) -> Iterator:
    """TestClient bound to the per-test DB. Rate-limit storage is
    in-process so each test starts with a clean budget."""
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.services.rate_limit import limiter

    limiter.reset()
    yield TestClient(app)


@pytest.fixture()
def admin_token(client) -> str:
    """Register a bootstrap admin and return their JWT."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@local.dev", "password": "admin1234", "name": "Admin"},
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


@pytest.fixture()
def admin_headers(admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def chapter_id(client, admin_headers) -> str:
    r = client.post("/api/v1/chapters", headers=admin_headers, json={"name": "Amsterdam"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture()
def organiser_token(client, admin_headers, chapter_id) -> str:
    """Register, manually verify, and admin-approve an organiser.
    Returns a logged-in token."""
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "organiser@local.dev", "password": "org12345", "name": "Organiser"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["user"]["id"]
    # Verify directly in DB — no email roundtrip in tests.
    from datetime import UTC, datetime

    from backend.database import SessionLocal
    from backend.models import User
    from backend.services import scd2

    db = SessionLocal()
    try:
        user = scd2.current_by_entity(db, User, uid)
        assert user is not None
        scd2.scd2_update(db, user, changed_by=user.entity_id, email_verified_at=datetime.now(UTC))
        db.commit()
    finally:
        db.close()
    # Approve via the admin endpoint.
    r = client.post(
        f"/api/v1/admin/users/{uid}/approve",
        headers=admin_headers,
        json={"chapter_id": chapter_id},
    )
    assert r.status_code == 200, r.text
    # Re-login so the JWT reflects the new approved state.
    r = client.post(
        "/api/v1/auth/login",
        json={"email": "organiser@local.dev", "password": "org12345"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def organiser_headers(organiser_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {organiser_token}"}
