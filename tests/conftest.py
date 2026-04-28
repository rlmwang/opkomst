"""Test fixtures.

A fresh per-test schema reset on a dedicated Postgres test database,
seeded with two users (``admin`` / ``organiser``) and one chapter
(``Amsterdam``) so individual tests can focus on their behaviour
rather than re-bootstrapping the world every time.

Each test gets its own ``TestClient`` bound to that DB; module
imports are kept inside fixtures so the app's startup-time
``run_migrations`` / ``run_seed`` don't fight per-test setup.

Local: ``make db-up`` runs once per dev session; the suite then
auto-creates an ``opkomst_test`` database next to the ``opkomst``
dev database. CI: GitHub Actions provides a ``postgres`` service
container with the same defaults.
"""

import os
import sys
from collections.abc import Iterator
from datetime import UTC

import psycopg
import pytest

# Dedicated test database — separate from the dev one so a stray
# ``pytest`` invocation can't trample seeded events. Auto-created
# below if missing. Override via ``TEST_DATABASE_URL`` if your CI /
# host setup uses different creds.
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://opkomst:opkomst@localhost:5433/opkomst_test",
)


def _ensure_test_database() -> None:
    """Create the test database if it doesn't exist. Connect to the
    administrative ``postgres`` database to issue the CREATE."""
    target_name = _TEST_DB_URL.rsplit("/", 1)[1]
    admin_url = _TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
    # ``psycopg.connect`` doesn't accept the SQLAlchemy ``+psycopg``
    # dialect prefix.
    admin_url = admin_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        cur = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (target_name,),
        )
        if cur.fetchone() is None:
            # Identifier interpolation: target_name is hard-coded
            # in this file, not user input.
            conn.execute(f'CREATE DATABASE "{target_name}"')


_ensure_test_database()
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-real-use")
os.environ.setdefault("EMAIL_ENCRYPTION_KEY", "19zJgFa6AyDoFI90PVOcY3/A8xH/3qXGyJt/hAVlCOA=")
os.environ.setdefault("EMAIL_BACKEND", "console")
os.environ.setdefault("MESSAGE_ID_DOMAIN", "test.opkomst.nu")
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:5173")
# Bootstrap email is read at module-import time in
# ``routers/auth.py``; setting it after imports would be a no-op.
# Override (not setdefault) because ``.env`` ships with an empty
# ``BOOTSTRAP_ADMIN_EMAIL=`` value — empty-but-set still counts
# as set for setdefault, so the test's expected admin email
# would never reach the auth router otherwise.
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "admin@local.dev"
# Override (not setdefault): a developer running tests after
# ``source .env`` would otherwise inherit ``LOCAL_MODE=1`` from
# their dev shell, which makes ``seed.run_local_demo`` create
# admin@local.dev / organiser@local.dev demo users at module
# import. Those rows survive the per-test ``Base.metadata.drop_all``
# only if the ORM object happens to live in the session, but the
# real fallout is that the seed *also* hits the bootstrap path
# in register, leaving the auth fixtures with a 409 they didn't
# expect. Tests own user creation; force the seed off here.
os.environ["LOCAL_MODE"] = "0"

# Repo root on sys.path so ``backend`` imports cleanly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_schema():
    """Run alembic migrations once per test session so the
    ``alembic_version`` table exists at HEAD. Without this the
    per-test ``Base.metadata.create_all`` would race the
    module-import-time ``run_migrations()`` inside
    ``backend.main``: the migrations would try to ``CREATE TABLE
    users`` on an already-populated schema and bail."""
    from backend.migrate import run_migrations

    run_migrations()
    yield


@pytest.fixture()
def db(_bootstrap_schema):
    """Per-test fresh DB. Drops all SCD2 chains between tests so
    state can't leak. The ``alembic_version`` table persists
    across drops because it's not in ``Base.metadata``; that's
    deliberate — once stamped at HEAD it stays valid."""
    from backend.database import Base, SessionLocal, engine

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


# ---- Env isolation ---------------------------------------------
#
# Optional env vars that change runtime behaviour. The autouse fixture
# clears them before every test so tests that don't explicitly opt in
# see the documented defaults — regardless of what's in the developer's
# shell, ``.env``, or a sibling test that called ``monkeypatch.setenv``.
#
# Required env vars (JWT_SECRET, EMAIL_ENCRYPTION_KEY, …) are set at
# module import in this file and must stay set; not listed here.
_OPTIONAL_TEST_ENV_VARS = (
    "SCALEWAY_WEBHOOK_SECRET",
    "OPKOMST_ALLOW_UNSIGNED_WEBHOOKS",
    "EMAIL_BATCH_SIZE",
    "EMAIL_RETRY_SLEEP_SECONDS",
)


@pytest.fixture(autouse=True)
def _isolate_optional_env(monkeypatch) -> None:
    """Clear every optional behaviour-changing env var before each
    test. Tests that need a specific value call
    ``monkeypatch.setenv(...)`` directly — those mutations
    auto-undo after the test, so the next test starts clean again."""
    for var in _OPTIONAL_TEST_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def fake_email() -> Iterator:
    """Replace the email backend with a recorder for the test's
    duration. The yielded ``FakeBackend`` exposes ``.sent`` (list
    of CapturedEmail) plus helpers like ``.to(addr)`` and
    ``.fail_n_times(addr, n)``. Auto-uninstalls in teardown so a
    later test starts clean."""
    from backend.services.email.testing import install_fake_backend, uninstall

    fake = install_fake_backend()
    try:
        yield fake
    finally:
        uninstall()


# ---- Frozen-clock fixture --------------------------------------

class _FrozenClock:
    """Wrapper around freezegun's ``freeze_time`` that lets a test
    advance the clock arbitrarily.

    Usage:
        def test_something(clock):
            clock.set("2026-04-27T10:00:00+00:00")
            ... do something ...
            clock.advance(hours=24)
            ... do something else ...

    The clock is frozen for the duration of the test; both
    ``datetime.now()`` and ``time.time()`` return the controlled
    value. Workers running inside the test see the simulated time.
    """

    def __init__(self) -> None:
        self._freezer = None
        self._frozen = None

    def set(self, when) -> None:  # accepts datetime or ISO string
        from datetime import datetime

        import freezegun

        if isinstance(when, str):
            when = datetime.fromisoformat(when)
        if self._freezer is not None:
            self._freezer.stop()
        self._freezer = freezegun.freeze_time(when)
        self._frozen = self._freezer.start()

    def advance(self, **kwargs) -> None:
        """Advance the frozen clock by a timedelta-friendly kwargs:
        ``hours``, ``days``, ``minutes``, etc. ``set`` must have
        been called first."""
        from datetime import timedelta

        if self._frozen is None:
            raise RuntimeError("Call clock.set(...) before clock.advance(...)")
        # freezegun's frozen handle is a callable that returns the
        # current frozen time. The simplest portable advance is to
        # stop the current freezer and start a new one at the
        # advanced time.
        delta = timedelta(**kwargs)
        new_time = self._frozen() + delta
        if new_time.tzinfo is None:
            new_time = new_time.replace(tzinfo=UTC)
        self.set(new_time)

    def stop(self) -> None:
        if self._freezer is not None:
            self._freezer.stop()
            self._freezer = None
            self._frozen = None


@pytest.fixture()
def clock() -> Iterator:
    """Frozen-clock helper. Tests that run workers / queries
    sensitive to time can ``clock.set(when)`` and ``clock.advance(
    hours=N)`` to simulate the passage of time without sleeping."""
    c = _FrozenClock()
    try:
        yield c
    finally:
        c.stop()
