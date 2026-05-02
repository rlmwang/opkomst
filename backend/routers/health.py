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
    db_ok = False
    schema_head: str | None = None
    oldest_pending_age_seconds: int | None = None
    # Disk-free under the working directory — picks up the volume
    # the SQLite-or-Postgres data + uploaded assets sit on. Below
    # 1 GB the runbook says page someone.
    try:
        usage = shutil.disk_usage(".")
        disk_free_gb = round(usage.free / (1024**3), 2)
    except Exception:
        disk_free_gb = None
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
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
        # ``status: ok`` only flips false when DB is unreachable;
        # everything else is best-effort introspection.
        pass
    finally:
        db.close()

    body: dict[str, object] = {
        "status": "ok" if db_ok else "degraded",
        "db_connectivity": db_ok,
        "schema_head": schema_head,
        "oldest_pending_dispatch_age_seconds": oldest_pending_age_seconds,
        "disk_free_gb": disk_free_gb,
        "email_executor_max_workers": get_executor()._max_workers,
    }
    # Return 503 when the DB is unreachable so plain HTTP-status
    # uptime monitors (UptimeRobot free tier, Sentry Uptime) catch
    # it without needing keyword-monitoring (which UptimeRobot
    # recently moved to paid plans). Body shape stays the same so
    # tooling that parses the JSON keeps working.
    return JSONResponse(content=body, status_code=200 if db_ok else 503)
