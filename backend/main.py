import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import cors_origins_list, settings
from .migrate import run_migrations
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import chapters as chapters_router
from .routers import events as events_router
from .routers import feedback as feedback_router
from .routers import signups as signups_router
from .routers import webhooks as webhooks_router
from .seed import run as run_seed
from .services.rate_limit import limiter
from .services.security_headers import SecurityHeadersMiddleware

logger = structlog.get_logger()

# Sentry — opt-in via env. ``SENTRY_DSN`` unset (dev / local) is a
# no-op. PII is OFF: ``send_default_pii=False`` keeps usernames /
# IPs out of events. The FastAPI / Starlette integrations capture
# 500s automatically. ``backend/cli.py`` runs the same init so
# scheduled-task exceptions also reach Sentry.
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info("sentry_initialized")

# Boot side-effects: migrations + seed + reaper pass. Skipped
# when ``OPKOMST_SKIP_BOOT=1`` so schema-generation scripts can
# import the app without touching the DB.
import os as _os  # noqa: E402

if _os.environ.get("OPKOMST_SKIP_BOOT") != "1":
    run_migrations()
    run_seed()


def _boot_reaper_pass() -> None:
    """One defensive sweep at API startup. The cron schedule
    handles steady state; this one catches whatever the previous
    process left mid-flight when it crashed (and a clean restart
    won't have any partial sends to clean up either way)."""
    from .database import SessionLocal
    from .services import email_reaper

    db = SessionLocal()
    try:
        email_reaper.reap_partial_sends(db)
    finally:
        db.close()


if _os.environ.get("OPKOMST_SKIP_BOOT") != "1":
    try:
        _boot_reaper_pass()
    except Exception:
        # A boot-time DB hiccup mustn't keep the API from coming up;
        # the cron will catch up at the next tick.
        logger.exception("boot_reaper_failed")


app = FastAPI(title="Opkomst", version="0.1.0")

# Rate limiting — installed before any router is included so the
# decorators on individual endpoints are honoured.
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(_request, exc: RateLimitExceeded):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests; retry later. Limit: {exc.detail}"},
    )


# Security headers on every response. Installed before CORS so
# CSP / HSTS / nosniff apply uniformly to preflights too.
app.add_middleware(SecurityHeadersMiddleware)

# CORS — dev frontend on 5173. In prod the frontend is served from the
# same origin so this becomes a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(chapters_router.router)
app.include_router(events_router.router)
app.include_router(signups_router.router)
app.include_router(feedback_router.router)
app.include_router(webhooks_router.router)


@app.get("/health")
def health() -> dict[str, object]:
    """Liveness probe + a few introspection knobs for ops.
    Includes the email-executor's bounded worker count so a
    deploy / config-change that accidentally lifted the cap is
    visible at a glance (Phase 4.3)."""
    from .services.email.backends import get_executor

    return {
        "status": "ok",
        "email_executor_max_workers": get_executor()._max_workers,
    }


# --- SPA serving ------------------------------------------------------
# In production the Vue build is copied to ``frontend/dist`` (see
# ``Dockerfile`` stage 1). We mount the ``assets`` folder with
# long-cache headers because Vite hashes filenames, then serve
# ``index.html`` for any other non-/api path so the client-side
# router can pick it up. Locally (``frontend/dist`` absent) the
# whole block silently no-ops.
import pathlib  # noqa: E402

from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    _DIST_RESOLVED = _DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:
        # ``StaticFiles`` already won the route for ``/assets/*``; this
        # handler covers everything else. We deliberately serve
        # ``index.html`` for unknown paths so the client-side router
        # can render its 404 page.
        if full_path.startswith("api/") or full_path == "health":
            # FastAPI's normal 404 — these would have been handled
            # by the matched router otherwise.
            raise HTTPException(status_code=404, detail="Not found")
        # Resolve the requested path and require it to live under the
        # dist directory; otherwise fall back to index.html. Without
        # this guard a request like ``/../../etc/passwd`` would happily
        # serve any readable file off the host.
        candidate = (_DIST / full_path).resolve()
        try:
            candidate.relative_to(_DIST_RESOLVED)
        except ValueError:
            return FileResponse(_DIST / "index.html")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
