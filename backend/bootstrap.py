"""Process-boot side effects: Sentry init.

Migrations used to live here too but have moved to
``backend/cli.py::migrate``. Running them at import time of
``backend.main`` raced when uvicorn spawned multiple workers —
each worker re-imports the app module, and N concurrent
``CREATE TABLE alembic_version`` calls collide on
``pg_type_typname_nsp_index``. The Dockerfile now chains
``python -m backend.cli migrate && uvicorn ...`` so the schema
is at HEAD before the supervisor forks; cron sweeps run their
own migration call (single-process, no race).
"""

import sentry_sdk
import structlog
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from .config import settings

logger = structlog.get_logger()


def init_sentry() -> None:
    """Opt-in via ``SENTRY_DSN``. PII is OFF; FastAPI / Starlette
    integrations capture 500s automatically. Idempotent and
    per-process — safe to call from every worker on import."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info("sentry_initialized")
