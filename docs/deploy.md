# Deploying opkomst

## Architecture

opkomst runs as **two processes** sharing one image:

* **`api`** — uvicorn behind whatever proxy Coolify gives you.
  Multiple replicas are fine. The Dockerfile bakes
  `DISABLE_SCHEDULER=1` so APScheduler stays off in every
  replica.
* **`worker`** — single replica, runs `python -m backend.worker`.
  Owns the reminder + feedback email sweeps. Override
  `DISABLE_SCHEDULER` to anything except `1` (or unset) on
  this container so the scheduler is allowed to boot.

Running the scheduler inside multiple replicas would fire each
scheduled email N times (one per replica), so the split is
not optional — it's a correctness requirement.

## Coolify (recommended)

1. Point Coolify at this repo. Build pack: **Dockerfile** (Coolify
   auto-detects `./Dockerfile`).
2. Set environment variables (paste from `.env.example`, fill in):
   - `JWT_SECRET` (32-byte url-safe token)
   - `EMAIL_ENCRYPTION_KEY` (32 raw bytes, base64)
   - `DATABASE_URL` (e.g. `postgres://opkomst:...@db:5432/opkomst`)
   - `EMAIL_BACKEND=smtp`
   - `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD`
   - `SMTP_FROM=noreply@opkomst.nu`
   - `MESSAGE_ID_DOMAIN=opkomst.nu`
   - `SCALEWAY_WEBHOOK_SECRET` (from the Scaleway TEM dashboard)
   - `PUBLIC_BASE_URL=https://opkomst.nu`
   - `BOOTSTRAP_ADMIN_EMAIL` (the email you'll register first)
   - `SENTRY_DSN` (optional)
3. Persistent storage: mount a volume at `/app/data` if you're using
   SQLite (`DATABASE_URL=sqlite:////app/data/opkomst.db`). For
   Postgres, no volume needed.
4. Health check: `GET /health` returns `200 {"status":"ok"}`. The
   Dockerfile has a built-in `HEALTHCHECK` so Coolify auto-discovers.
5. Migrations run on startup via `backend/migrate.py`. The first
   deploy applies the full chain.
6. Webhook URL for Scaleway TEM:
   `https://opkomst.nu/api/v1/webhooks/scaleway-email`. Paste the
   webhook secret into `SCALEWAY_WEBHOOK_SECRET`.
7. Add a **second service** in Coolify, same git repo + same
   image, with these overrides:
   - **Custom start command:**
     `uv run --no-dev python -m backend.worker`
   - **Environment variable:** `DISABLE_SCHEDULER=0`
   - **Replicas:** 1 (single replica is required — see
     "Architecture" above).
   - **No exposed ports** — this service has no HTTP surface.
   - **Healthcheck:** disable; the worker has no /health endpoint.
   Mount the same `/app/data` volume if you're on SQLite. Both
   services share the same DB.

## Local production smoke

```bash
docker compose up --build
```

Brings up `api` (port 8000) + `worker` (background) using the
same image. Open `http://localhost:8000` for the SPA; the
worker's stdout shows `worker_started` and per-tick sweeps.

Or, single-container API only (no email sweeps):

```bash
docker build -t opkomst:latest .
docker run --rm -p 8000:8000 \
    --env-file .env \
    -v $(pwd)/data:/app/data \
    opkomst:latest
```

## Operations

### Rotating secrets

- **`JWT_SECRET`** — invalidates every existing session. Users get
  re-prompted to log in. No data loss.
- **`EMAIL_ENCRYPTION_KEY`** — invalidates every encrypted email
  blob currently in flight. Any signup whose email hasn't been
  decrypted yet (status: `pending`) loses the ability to receive a
  feedback email; the worker will mark them `failed` and wipe the
  blob. Plan rotation around an event boundary.
- **`SCALEWAY_WEBHOOK_SECRET`** — must match the value in the
  Scaleway TEM dashboard. Bounce / complaint events submitted with
  the wrong signature get rejected.

### Backups

SQLite: copy the file at `/app/data/opkomst.db`. Postgres: standard
`pg_dump`. The schema is small (~10 tables); restoring on a fresh
host runs migrations to head and then loads the dump.

### Monitoring

`structlog` lines hit stdout. Coolify aggregates them. With `SENTRY_DSN`
set, all unhandled exceptions land in Sentry. PII is OFF
(`send_default_pii=False`); structured logs deliberately omit emails,
display names, and IP addresses.
