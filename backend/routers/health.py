"""Liveness probe + ops introspection.

Two routes, deliberately split:

* ``GET /health`` — cheap. No DB hit, no syscalls, no
  introspection. Returns a constant ``{"status": "ok"}`` as fast
  as Python can serialise it. This is what Coolify's container
  healthcheck pings every 30 s; before the split, it ran the full
  introspection (DB SELECT 1, alembic head lookup, oldest pending
  scan, ``shutil.disk_usage``) on every tick, contributing to
  observed handler-side stalls in the slow_request log.
* ``GET /health/full`` — the introspection payload (schema head,
  oldest pending dispatch age, disk free, executor cap, DB
  connectivity). Used by UptimeRobot's keyword monitor (catches
  DB-degraded via ``"status":"ok"`` keyword check), ops curl, and
  the runbook scenario playbooks.
"""

import shutil
import threading
import time
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..database import SessionLocal
from ..models import EmailDispatch, EmailStatus
from ..services.mail import get_executor

router = APIRouter()


# GET serves the actual contract; HEAD is registered as a
# parallel route so uptime monitors (UptimeRobot, Sentry Uptime)
# that default to HEAD don't 405 and report the site as down.
# HEAD is excluded from the OpenAPI schema (``include_in_schema
# =False``) because it's a transport concern — including it
# emits duplicate operationIds and breaks openapi-typescript
# codegen on the frontend. Starlette strips the body on HEAD
# automatically so the handler stays GET-shaped.


@router.head("/health", include_in_schema=False)
@router.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness — Coolify pings this every 30 s. A 2xx
    response is the only contract; deeper introspection lives on
    ``/health/full``."""
    return {"status": "ok"}


# Coolify's container healthcheck + UptimeRobot together hit
# ``/health/full`` ~3×/min; on a memory-pressured host each tick
# costs a worker the disk_usage syscall, the alembic version
# SELECT, and an EmailDispatch index scan. None of that data
# changes on the seconds-scale, so the introspection payload is
# cached for ``_HEALTH_FULL_TTL`` and reused. Live ``SELECT 1``
# still runs on every request so a downed DB is reported within
# one tick (the 503 contract is unchanged).
_HEALTH_FULL_TTL = 15.0
_health_full_lock = threading.Lock()
_health_full_cache: dict[str, object] | None = None
_health_full_expires_at: float = 0.0


def _reset_health_full_cache() -> None:
    """Drop the cached introspection payload. Test fixtures call
    this between tests so a prior healthy run can't mask a
    monkeypatched-DB-down assertion."""
    global _health_full_cache, _health_full_expires_at
    with _health_full_lock:
        _health_full_cache = None
        _health_full_expires_at = 0.0


@router.head("/health/full", include_in_schema=False)
@router.get("/health/full")
def health_full() -> JSONResponse:
    """Liveness + ops introspection.

    Beyond ``status: ok``, the response surfaces:
    * email-executor bounded worker count — a deploy that
      accidentally lifted the cap is visible at a glance;
    * Alembic schema head — the migration revision the running
      process believes the DB is at, so a Coolify deploy that
      forgot to run migrations is one curl away from being
      caught;
    * DB connectivity — a trivial ``SELECT 1`` round-trip;
    * oldest pending dispatch — surfaces a stuck queue (worker
      crashed, SMTP outage, etc.) before it shows up in user
      complaints.
    """
    global _health_full_cache, _health_full_expires_at
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db.close()
        body: dict[str, object] = {
            "status": "degraded",
            "db_connectivity": False,
            "schema_head": None,
            "oldest_pending_dispatch_age_seconds": None,
            "disk_free_gb": None,
            "email_executor_max_workers": get_executor()._max_workers,
        }
        return JSONResponse(content=body, status_code=503)

    now = time.monotonic()
    with _health_full_lock:
        cached = _health_full_cache
        fresh = cached is not None and now < _health_full_expires_at
    if fresh:
        db.close()
        return JSONResponse(content=cached, status_code=200)

    schema_head: str | None = None
    oldest_pending_age_seconds: int | None = None
    # Disk-free under the working directory — picks up the volume
    # the SQLite-or-Postgres data + uploaded assets sit on. Below
    # 1 GB the runbook says page someone.
    try:
        usage = shutil.disk_usage(".")
        disk_free_gb: float | None = round(usage.free / (1024**3), 2)
    except Exception:
        disk_free_gb = None
    try:
        head_row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        schema_head = head_row[0] if head_row else None
        oldest = (
            db.query(EmailDispatch.created_at)
            .filter(EmailDispatch.status == EmailStatus.PENDING)
            .order_by(EmailDispatch.created_at.asc())
            .first()
        )
        if oldest is not None:
            age = datetime.now(UTC) - oldest[0]
            oldest_pending_age_seconds = int(age.total_seconds())
    except Exception:
        # Best-effort introspection: ``SELECT 1`` already passed
        # so ``status`` stays "ok"; a transient failure on the
        # follow-up queries leaves their fields ``None``.
        pass
    finally:
        db.close()

    body = {
        "status": "ok",
        "db_connectivity": True,
        "schema_head": schema_head,
        "oldest_pending_dispatch_age_seconds": oldest_pending_age_seconds,
        "disk_free_gb": disk_free_gb,
        "email_executor_max_workers": get_executor()._max_workers,
    }
    with _health_full_lock:
        _health_full_cache = body
        _health_full_expires_at = now + _HEALTH_FULL_TTL
    return JSONResponse(content=body, status_code=200)
