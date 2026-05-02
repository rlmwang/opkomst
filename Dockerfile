# syntax=docker/dockerfile:1.7
#
# Multi-stage build:
#   1. ``frontend-builder``  builds the Vue/Vite SPA into ``frontend/dist``.
#   2. ``backend-runtime``   installs Python deps with ``uv``, copies the
#                            backend source and the built SPA, and runs
#                            uvicorn with multiple workers.
#
# Build:
#   docker build -t opkomst:latest .
#
# Run (bind-mounting the SQLite file for local prod testing):
#   docker run --rm -p 8000:8000 \
#     --env-file .env \
#     -v $(pwd)/data:/app/data \
#     opkomst:latest
#
# Coolify-friendly: exposes port 8000, healthcheck on ``GET /health``.

# ---------------------------------------------------------------------------
# Stage 1 — frontend bundle
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
# Cache mount for the npm registry — incremental rebuilds skip
# the ~30 s network fetch for the same dep tree. ``npm ci`` still
# runs (it validates the lock + installs into ``node_modules``),
# but tarballs come from the cache instead of the network.
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime
# ---------------------------------------------------------------------------
# python:3.13-slim (Debian-based). Tried alpine — the image saves
# ~100 MB but Coolify's first build with a new base downloaded
# the image, populated a fresh musllinux wheel cache, and ran
# ~50% slower (4.5 min vs 3 min on slim). BuildKit
# ``--mount=type=cache`` doesn't persist between Coolify deploys,
# so the speed-up never materialised. For a few-deploys-per-day
# project the build cost outweighs the size win — staying on
# slim where Coolify's existing layer cache is already warm.
FROM python:3.13-slim AS backend-runtime

# uv via the pinned image — same tool as local dev.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# System deps: ``libpq5`` for psycopg's runtime,
# ``postgresql-client`` for the daily ``scripts/backup.sh`` cron
# (needs ``pg_dump`` — without it the cron fails AFTER the
# redactor pipeline starts and writes silently mangled backups),
# ``curl`` for the Dockerfile HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Lockfile-only install — keeps the layer cached when only source
# files change. ``--mount=type=cache`` reuses uv's resolved
# wheel store across builds; an unchanged lock is a sub-second
# resolve instead of a 30–60 s redownload.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# App source.
COPY backend/ ./backend/

# Cron-runner scripts. ``scripts/backup.sh`` is invoked by a
# Coolify scheduled task and needs to exist inside the image.
COPY scripts/ ./scripts/

# SPA bundle into the location FastAPI's StaticFiles mount expects.
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Non-root user for the runtime.
RUN useradd --create-home --uid 1000 opkomst \
    && mkdir -p /app/data \
    && chown -R opkomst:opkomst /app
USER opkomst

EXPOSE 8000

# Healthcheck timing tuned to actual startup cost:
# * ``cli migrate`` (alembic to-head check, even no-op) ~5–10 s
# * uvicorn boot + 2-worker fork ~5–10 s
# * each worker imports the app + runs the lifespan warmup ~5 s
# Observed ~80 s total to first ``GET /health`` 200 in Coolify.
# ``start-period=60s`` skips healthcheck failures during normal
# startup (first real check fires at +60s instead of +15s, which
# was failing the first 2 of 3 attempts and adding ~30 s to
# every deploy). After ``start_period`` regular ``interval=10s``
# kicks in for fast detection of actual unhealthy state.
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Two workers halves GIL contention — sync routes run in a thread
# pool, so a CPU-heavy span on one worker (Pydantic validation,
# response serialisation) doesn't stall an unrelated request as
# easily. Diagnosed via Server-Timing telemetry: PUTs landing at
# ~300 ms with only ~30 ms in DB, no fresh connection involved,
# pointed at handler-side serialisation. Override via
# ``WEB_CONCURRENCY`` env if needed.
ENV WEB_CONCURRENCY=2

# The image's default CMD is the API. Scheduled email sweeps run
# as cron-style one-shots via ``python -m backend.cli ...`` — see
# ``docs/deploy.md`` for the cron stanzas. Same image, different
# command per cron; no separate long-running worker container.
#
# The shell-form CMD chains a one-shot ``cli migrate`` before
# uvicorn so migrations land on the schema once — running them
# from inside ``backend.main``'s import path raced with
# ``WEB_CONCURRENCY > 1`` (every worker re-imported and N parallel
# ``CREATE TABLE alembic_version`` calls collided on
# ``pg_type_typname_nsp_index``). ``exec`` hands PID 1 to uvicorn
# so signals propagate cleanly.

CMD uv run --no-dev python -m backend.cli migrate && \
    exec uv run --no-dev uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY}
