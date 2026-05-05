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
from pathlib import Path

import hypothesis
import psycopg
import pytest
from hypothesis import HealthCheck

# Dedicated test database — separate from the dev one so a stray
# ``pytest`` invocation can't trample seeded events. Auto-created
# below if missing. Override via ``TEST_DATABASE_URL`` if your CI /
# host setup uses different creds.
#
# Under pytest-xdist each worker needs its own isolated database;
# otherwise their per-test ``TRUNCATE`` calls collide. xdist sets
# ``PYTEST_XDIST_WORKER=gw0`` (etc.) — we suffix the DB name with
# that. Single-process runs (no xdist) just use ``opkomst_test``.
_BASE_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://opkomst:opkomst@localhost:5433/opkomst_test",
)
_xdist_worker = os.environ.get("PYTEST_XDIST_WORKER")
if _xdist_worker:
    _TEST_DB_URL = f"{_BASE_TEST_DB_URL}_{_xdist_worker}"
else:
    _TEST_DB_URL = _BASE_TEST_DB_URL


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


# Hypothesis profiles. Local dev (the default ``dev`` profile, used
# by lefthook's pre-push hook) runs few examples for fast feedback;
# CI bumps the budget to catch tail-edge cases. Activate the CI
# profile by setting the ``CI`` env var (GitHub Actions sets it
# automatically). Per-test ``@settings`` decorators that omit
# ``max_examples`` inherit from the loaded profile — the profile
# is the source of truth for fuzz budget.
hypothesis.settings.register_profile(
    "dev",
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
hypothesis.settings.register_profile(
    "ci",
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
hypothesis.settings.load_profile("ci" if os.environ.get("CI") else "dev")


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
# their dev shell, which enables the ``/auth/dev-verify`` magic-
# link helper in ``routers/auth.py``. Tests exercise the real
# magic-link round-trip; force the dev shortcut off so the test
# surface matches production.
os.environ["LOCAL_MODE"] = "0"

# Repo root on sys.path so ``backend`` imports cleanly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_schema():
    """Run alembic migrations once per test session so the
    ``alembic_version`` table exists at HEAD.

    Skip the upgrade if the DB is already stamped at the head
    revision — for warm test DBs (the common case under xdist
    where ``opkomst_test_<worker>`` databases persist between
    runs) this saves ~1.5 s of per-worker startup. The first
    cold run still pays the migration cost; subsequent runs hit
    the fast path."""
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text

    from backend.config import settings
    from backend.database import engine

    cfg_path = Path(__file__).parents[1] / "backend" / "alembic.ini"
    inspector = inspect(engine)
    if inspector.has_table("alembic_version"):
        from alembic.config import Config

        cfg = Config(str(cfg_path))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        head_rev = ScriptDirectory.from_config(cfg).get_current_head()
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if current == head_rev:
            yield
            return

    from backend.migrate import run_migrations

    run_migrations()
    yield


@pytest.fixture()
def db(_bootstrap_schema):
    """Per-test clean slate via ``TRUNCATE ... CASCADE``.

    The previous implementation dropped and re-created the entire
    schema between every test; on a 250-test suite that was the
    dominant cost (~120 ms × N from re-running CREATE TABLE).
    ``TRUNCATE`` keeps the schema in place, leaves the alembic
    version stamp intact, and is one round-trip per test instead
    of dozens — roughly 10× faster end-to-end.

    ``RESTART IDENTITY CASCADE`` resets any sequences and follows
    FKs so we don't have to truncate in dependency order. The
    ``alembic_version`` table is never in ``Base.metadata`` and
    is deliberately excluded from the truncate set."""
    from backend.database import SessionLocal
    from tests._helpers.db_reset import truncate_all

    truncate_all()
    # ``/health/full`` caches its introspection payload for ~15 s
    # in-process; clear between tests so a prior healthy run can't
    # mask a monkeypatched-DB-down assertion or stale schema_head.
    from backend.routers.health import _reset_health_full_cache

    _reset_health_full_cache()
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
def admin_token(db) -> str:
    """Insert an approved admin row directly and mint a JWT.

    The full magic-link sign-up flow is exercised by dedicated
    tests in ``test_auth.py`` (which call ``register_user``
    directly). For every other test that just needs an admin
    actor, the HTTP round-trip is pure overhead — this fixture
    skips it and inserts the row in one commit."""
    from backend.auth import create_token
    from backend.models import User

    user = User(
        email="admin@local.dev",
        name="Admin",
        role="admin",
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return create_token(user.id)


@pytest.fixture()
def admin_headers(admin_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def chapter_id(db) -> str:
    """Insert a Chapter row directly and return its id. Same
    skip-the-HTTP rationale as ``admin_token``."""
    from backend.models import Chapter

    chapter = Chapter(name="Amsterdam")
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter.id


@pytest.fixture()
def organiser_token(db, admin_token, chapter_id) -> str:
    """Insert an approved organiser row with a chapter membership
    and mint a JWT. Same skip-the-HTTP rationale as
    ``admin_token`` — dedicated auth tests cover the real flow.

    Depends on ``admin_token`` to preserve the previous fixture
    chain's invariant that an admin row exists whenever an
    organiser does. Several tests assume both populate the user
    table together; the dependency keeps that contract."""
    from backend.auth import create_token
    from backend.models import User, UserChapter

    user = User(
        email="organiser@local.dev",
        name="Organiser",
        role="organiser",
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserChapter(user_id=user.id, chapter_id=chapter_id))
    db.commit()
    return create_token(user.id)


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


# ---- Per-test perf guard ---------------------------------------
#
# Records every test's call-phase duration and emits a terminal
# summary at session end listing any test over budget. Catches
# regressions like the ``drop_all + create_all`` Hypothesis pattern
# that turned single tests into ~40 s monsters before we noticed.
#
# Soft signal — does not fail the run. Bumped to a hard failure by
# setting ``OPKOMST_PERF_STRICT=1`` (good for a periodic CI job).
# Per-test budget: 3 s. The Hypothesis property tests legitimately
# sit just under that on the CI profile; routine router tests are
# under 200 ms. Anything above 3 s is almost certainly a bug.

_PERF_BUDGET_SECONDS = 3.0
_test_durations: dict[str, float] = {}

# Bind ``time.monotonic`` at conftest-import time. Freezegun
# rewrites ``time.monotonic`` *attribute* on the module when a
# test calls ``freeze_time`` — the local reference here keeps the
# original C function, so the perf guard measures real wall-clock
# rather than the (frozen) test clock. Without this, every test
# that uses ``clock`` reports duration ≈ epoch seconds.
from time import monotonic as _real_monotonic  # noqa: E402


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):  # type: ignore[no-untyped-def]
    start = _real_monotonic()
    outcome = yield
    _test_durations[item.nodeid] = _real_monotonic() - start
    return outcome


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # type: ignore[no-untyped-def]
    over = [(n, t) for n, t in _test_durations.items() if t > _PERF_BUDGET_SECONDS]
    if not over:
        return
    over.sort(key=lambda nt: -nt[1])
    terminalreporter.write_sep("=", f"tests over {_PERF_BUDGET_SECONDS}s budget", yellow=True)
    for nodeid, t in over:
        terminalreporter.write_line(f"  {t:6.2f}s  {nodeid}")
    if os.environ.get("OPKOMST_PERF_STRICT"):
        # Tip the run red: budget overruns are real failures under strict mode.
        # Same exit code pytest uses for test failures.
        raise SystemExit(1)


@pytest.fixture()
def fake_email() -> Iterator:
    """Replace the email backend with a recorder for the test's
    duration. The yielded ``FakeBackend`` exposes ``.sent`` (list
    of CapturedEmail) plus helpers like ``.to(addr)`` and
    ``.fail_n_times(addr, n)``. Auto-uninstalls in teardown so a
    later test starts clean."""
    from backend.services.mail import install_fake_backend, uninstall_fake_backend

    fake = install_fake_backend()
    try:
        yield fake
    finally:
        uninstall_fake_backend()


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
