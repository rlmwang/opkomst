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
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS backend-runtime

# uv via the pinned image — same tool as local dev.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# System deps: just the bare minimum for psycopg2/Pillow/qrcode runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Lockfile-only install — keeps the layer cached when only source
# files change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# App source.
COPY backend/ ./backend/

# SPA bundle into the location FastAPI's StaticFiles mount expects.
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Non-root user for the runtime.
RUN useradd --create-home --uid 1000 opkomst \
    && mkdir -p /app/data \
    && chown -R opkomst:opkomst /app
USER opkomst

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# 4 workers is a reasonable default for a small VPS; override via
# ``WEB_CONCURRENCY`` env if needed.
ENV WEB_CONCURRENCY=4

# The image's default CMD is the API. Scheduled email sweeps run
# as cron-style one-shots via ``python -m backend.cli ...`` — see
# ``docs/deploy.md`` for the cron stanzas. Same image, different
# command per cron; no separate long-running worker container.

CMD ["uv", "run", "--no-dev", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
