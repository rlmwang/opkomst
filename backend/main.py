from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .bootstrap import init_sentry
from .config import cors_origins_list, settings
from .database import engine
from .routers import admin as admin_router
from .routers import auth as auth_router
from .routers import chapters as chapters_router
from .routers import events as events_router
from .routers import events_public as events_public_router
from .routers import feedback as feedback_router
from .routers import health as health_router
from .routers import signups as signups_router
from .routers import spa
from .services.observability import TimingMiddleware
from .services.observability import install as install_timing
from .services.rate_limit import limiter
from .services.security_headers import SecurityHeadersMiddleware

# Sentry init is per-process and idempotent, safe at every worker
# import. Migrations are NOT — when ``WEB_CONCURRENCY > 1`` every
# uvicorn worker re-imports this module and N concurrent
# ``CREATE TABLE alembic_version`` calls collide on
# ``pg_type_typname_nsp_index``. Migrations now run as a one-shot
# ``python -m backend.cli migrate`` chained before uvicorn in the
# Dockerfile CMD; cron sweeps run them themselves before their
# own work (single-process, no race).
init_sentry()
install_timing(engine)


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    """Per-worker startup: pre-warm the DB pool + SQLAlchemy
    compilation cache so the first real request a worker handles
    doesn't pay one-shot per-query-shape compilation costs.
    Multi-worker (``--workers 2``) makes this matter: each worker
    pays its own warmup separately."""
    from .database import warmup as _warmup_db

    _warmup_db()
    yield


app = FastAPI(title="Opkomst", version="0.1.0", lifespan=_lifespan)

# Rate limiting — installed before any router is included so the
# decorators on individual endpoints are honoured.
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(_request, exc: RateLimitExceeded):  # type: ignore[no-untyped-def]
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests; retry later. Limit: {exc.detail}"},
    )


# Security headers on every response. Installed before CORS so
# CSP / HSTS / nosniff apply uniformly to preflights too.
app.add_middleware(SecurityHeadersMiddleware)

# Gzip everything ≥1 KiB. The static SPA bundle (~470 KB raw PrimeVue
# chunk, ~190 KB main) compresses ~4× and is the dominant payload on
# first paint.
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS — dev frontend on 5173. In prod the frontend is served from the
# same origin so this becomes a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide non-CORS-safelisted headers from cross-origin
    # JS by default; expose Server-Timing so DevTools can render
    # the breakdown when the frontend is on a different origin
    # (dev: 5173 → 8000).
    expose_headers=["Server-Timing"],
)

# Timing middleware added LAST so it sits OUTERMOST in the
# Starlette stack — measures the full server-side duration the
# client observes, including rate-limit rejections, CORS
# preflights, and security-header costs.
app.add_middleware(TimingMiddleware)

app.include_router(auth_router.router)
app.include_router(admin_router.router)
app.include_router(chapters_router.router)
app.include_router(events_router.router)
app.include_router(events_public_router.router)
app.include_router(signups_router.router)
app.include_router(feedback_router.router)
app.include_router(health_router.router)

# Local-mode-only routes (dev-issue-token et al). Mounted iff
# ``settings.local_mode`` is True so prod simply 404s on these
# paths — no per-route gate needed.
if settings.local_mode:
    from .routers import dev as dev_router

    app.include_router(dev_router.router)

# SPA fallback last so router matches win first.
spa.mount(app)
