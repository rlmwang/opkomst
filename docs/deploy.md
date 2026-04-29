# Deploying opkomst

## Architecture

opkomst runs as **one image, two invocation patterns**:

* **API** — uvicorn behind whatever proxy Coolify gives you.
  Multiple replicas are fine — they're stateless.
* **Cron jobs** — same image, different command per cadence,
  invoked by Coolify's "Scheduled Tasks" feature. See § 7 below
  for the cron stanzas.

Multi-replica safety is structural: only the cron host fires, so
scaling the API up doesn't double-send any email. There's no
long-running scheduler container to coordinate.

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
3. No application-side volume needed — Postgres is the durable
   store, and Coolify handles its volume separately. Set
   `DATABASE_URL=postgresql+psycopg://…` to whichever managed
   Postgres instance you've provisioned.
4. Health check: `GET /health` returns `200 {"status":"ok"}`. The
   Dockerfile has a built-in `HEALTHCHECK` so Coolify auto-discovers.
5. Migrations run on startup via `backend/migrate.py`. The first
   deploy applies the full chain.
6. Webhook URL for Scaleway TEM:
   `https://opkomst.nu/api/v1/webhooks/scaleway-email`. Paste the
   webhook secret into `SCALEWAY_WEBHOOK_SECRET`.
7. **Scheduled email sweeps** — Coolify's "Scheduled Tasks" feature
   invokes the same image with a different command on each cadence.
   Six jobs total; offset minutes so they don't all hit the DB at
   once:

   ```
   0  *  * * *   uv run --no-dev python -m backend.cli dispatch reminder
   0  *  * * *   uv run --no-dev python -m backend.cli dispatch feedback
   30 *  * * *   uv run --no-dev python -m backend.cli reap-partial
   0  3  * * *   uv run --no-dev python -m backend.cli reap-expired
   30 3  * * *   uv run --no-dev python -m backend.cli reap-post-event-emails
   45 3  * * *   uv run --no-dev python -m backend.cli reap-login-tokens
   ```

   Each command does one sweep and exits. A non-zero exit becomes a
   Coolify alert (and a Sentry exception if `SENTRY_DSN` is set);
   we don't want one tick's hiccup to silently mask a real bug, so
   the CLI deliberately re-raises instead of swallowing.

   Multi-replica safety is structural — only the cron host fires —
   so unlike a long-running scheduler container, you can scale the
   API replicas without doubling email sends.

## Rate limiting (SlowAPI storage)

Opkomst uses ``slowapi`` for per-IP rate limits. The default
storage backend is in-process memory (``memory://``), which means
each replica counts independently — running ``N`` replicas
multiplies effective limits by ``N``.

**Decision: opkomst runs as a single API replica**, behind
Coolify's reverse proxy. Email volume + traffic make horizontal
scaling unnecessary at the foreseeable scale, and a single replica
keeps SlowAPI's defaults correct without operating a separate
Redis instance for rate-limit state alone.

If you ever need to scale to multiple replicas, set
``RATE_LIMIT_STORAGE_URI=redis://<host>:6379/0`` in the Coolify
env so the limiter shares a counter across instances. The
``Settings`` model already accepts the variable; no code change is
required.

## Local production smoke

```bash
docker compose up --build
```

Brings up `api` (port 8000) + `postgres` using the
same image. Open `http://localhost:8000` for the SPA. To exercise
a sweep locally:

```bash
docker compose run --rm api python -m backend.cli dispatch reminder
```

Or, single-container API only (no DB):

```bash
docker build -t opkomst:latest .
docker run --rm -p 8000:8000 \
    --env-file .env \
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

Postgres: standard `pg_dump`. The schema is small (~10 tables);
restoring on a fresh host runs migrations to head and then loads
the dump.

### Monitoring

`structlog` lines hit stdout. Coolify aggregates them. With `SENTRY_DSN`
set, all unhandled exceptions land in Sentry. PII is OFF
(`send_default_pii=False`); structured logs deliberately omit emails,
display names, and IP addresses.
