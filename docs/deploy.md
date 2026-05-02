# Deploying opkomst

End-to-end production setup. One pass top-to-bottom and you have
a working, monitored, backed-up opkomst deployment. The
"Operations" section at the end covers everything that comes
after the first green deploy.

## Upgrade notes — magic-link registration unification

If you're upgrading an already-deployed instance to the
"unified magic-link sign-up" change:

1. **Coolify → Scheduled Tasks**: rename the daily token-reap
   job's command from ``python -m backend.cli reap-login-tokens``
   to ``python -m backend.cli reap-auth-tokens`` (same `45 3 * * *`
   schedule). The old subcommand is gone — leaving the task as-is
   will cause cron failures.
2. **Sentry → Crons**: the slug emitted by the new command is
   ``opkomst-cli-reap-auth-tokens`` and is upserted automatically
   on the first run. The old ``opkomst-cli-reap-login-tokens``
   monitor will go silent and eventually self-archive — safe to
   delete it manually after the new monitor records its first
   green check-in.
3. **No data migration needed.** The new ``registration_tokens``
   table is empty on first deploy; the alembic migration creates
   it. Existing ``login_tokens`` rows keep working unchanged.
4. **No frontend route to redirect.** ``/register`` is gone; the
   single entry point is ``/login``. Any bookmarks fall through
   to the SPA's NotFound page. If a redirect matters for SEO,
   add it at the proxy layer.

Replace ``opkomst.nu`` with whatever domain you actually own.
Replace ``203.0.113.42`` with your Coolify host's IP.

## Architecture

Opkomst runs as **one image, two invocation patterns** behind
Coolify:

* **API** — uvicorn behind Coolify's reverse proxy, serving both
  the FastAPI routes (``/api/v1/*``, ``/health``) and the Vue
  SPA (every other path). Stateless.
* **Cron jobs** — same image, different ``python -m backend.cli
  <verb>`` per cadence, invoked by Coolify's "Scheduled Tasks"
  feature. Each invocation does one sweep and exits. No
  long-running scheduler container.

Multi-replica safety is structural: only the cron host fires
sweeps, so scaling the API up doesn't double-send any email. We
deliberately run a **single API replica** anyway — see "Rate
limiting" under Operations for why.

## 1. Generate secrets

Two secrets to mint before you touch Coolify. Keep them in a
password manager; they go into env vars in step 4 and are *not*
recoverable.

```bash
# JWT_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"

# EMAIL_ENCRYPTION_KEY (32 raw bytes, base64-encoded)
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

## 2. DNS

In your domain registrar:

```
opkomst.nu         A       203.0.113.42
www.opkomst.nu     CNAME   opkomst.nu
```

Wait for propagation (``dig opkomst.nu`` returns the IP).

## 3. Scaleway TEM

For ``EMAIL_BACKEND=smtp`` to work. Domain verification takes
minutes-to-hours, so kick this off now and it'll be ready by the
time you hit step 5.

1. Sign up at https://console.scaleway.com → **Transactional
   Email** → **Create domain** → ``opkomst.nu``.
2. Scaleway gives you DNS records to add (SPF, DKIM, DMARC).
   Add them at your registrar alongside the records from step 2.
   Verification fires automatically once they propagate.
3. Once verified, **Create credentials** for SMTP. Save
   ``SMTP_USER`` (your Project ID) and ``SMTP_PASSWORD`` (the
   API Secret Key) for step 5.
4. **Attach IAM policy.** Scaleway console → **IAM → API Keys**
   → click the key you just minted → add the
   ``TransactionalEmailEmailFullAccess`` permission set. Without
   it, SMTP auth fails with ``535 5.7.8 Permission denied``
   even though the domain is verified — the key authenticates
   to Scaleway but isn't authorised against the TEM service.

**If your VPS is on Scaleway**, use port **2587**, not 587.
Scaleway's anti-abuse policy blocks outbound 587 / 465 / 25 at
the instance network level; their TEM service exposes submission
on the alternate port 2587 with the same STARTTLS protocol. The
``smtplib.connect timed out`` you'd otherwise hit on first
register is exactly this — port 587 is reachable from anywhere
*else*, so the failure looks magical until you realise it's a
provider-level block. Other VPS providers (Hetzner, OVH, etc.)
generally allow 587; if you're not on Scaleway, leave it at 587.

Opkomst doesn't ingest TEM webhook events: Scaleway gates them
behind a paid Cockpit topic, and the only thing the integration
ever did was surface bounce / complaint counts on the
email-health dashboard. The TEM dashboard already shows the
same data; check there if delivery starts looking off.

## 4. Coolify project + Postgres

In Coolify:

1. **New Project** → "opkomst".
2. **+ New Resource → Postgres**:
   - Name: ``opkomst-db``
   - Postgres version: 16
   - DB / user / password: pick any. Coolify gives you a
     ``DATABASE_URL`` once it's running.
3. **+ New Resource → Application → Public Repository**:
   - URL: your fork of opkomst on GitHub.
   - Build pack: Dockerfile (Coolify auto-detects ``./Dockerfile``).
   - Domain: ``https://opkomst.nu`` (Coolify provisions
     Let's Encrypt automatically once DNS is in).
4. **Add a Persistent Volume** for backups: Coolify → application →
   Storage → **+ Add Persistent Storage** → mount path
   ``/app/data``. The daily ``scripts/backup.sh`` cron writes
   ``opkomst-<UTC-stamp>.sql.gz`` files into ``/app/data/backups``
   (the configurable ``BACKUP_DIR`` defaults to that path).
   Without the volume, backups land in ephemeral container
   storage and disappear on the next deploy. Postgres data lives
   in its own Coolify-managed volume — that's separate.

## 5. Application env vars

Coolify → application → Environment Variables. Paste these in,
substituting your secrets from step 1, the TEM credentials from
step 3, and the ``DATABASE_URL`` from step 4.

```ini
# Required
JWT_SECRET=<from step 1>
EMAIL_ENCRYPTION_KEY=<from step 1>
DATABASE_URL=<from Coolify Postgres service>
PUBLIC_BASE_URL=https://opkomst.nu
CORS_ORIGINS=https://opkomst.nu
MESSAGE_ID_DOMAIN=opkomst.nu

# Email — note port 2587, not the SMTP-standard 587. Scaleway
# blocks outbound 587 / 465 / 25 from their VPS instances at the
# network level (anti-abuse) and exposes TEM submission on the
# alternate port 2587 with the same STARTTLS protocol. Same host,
# same creds, only the port differs from generic SMTP docs.
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.tem.scw.cloud
SMTP_PORT=2587
SMTP_USER=<from step 3>
SMTP_PASSWORD=<from step 3>
SMTP_FROM=noreply@opkomst.nu

# Bootstrap admin: the very first registration with this email
# auto-promotes to admin. Set to your own email.
BOOTSTRAP_ADMIN_EMAIL=you@example.com

# Sentry — fill in after step 9. Both backend and frontend read
# the same DSN; the frontend reads VITE_-prefixed copies because
# Vite only injects those into the client bundle.
SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0
VITE_SENTRY_DSN=
VITE_SENTRY_ENVIRONMENT=production
VITE_SENTRY_TRACES_SAMPLE_RATE=0

# Backups — used by scripts/backup.sh in step 7. Default
# /app/data/backups maps to a Coolify Persistent Volume mounted at
# /app/data; without that mount the cron writes to ephemeral
# container storage and the file vanishes on the next deploy.
BACKUP_DIR=/app/data/backups
RETENTION_DAYS=30

# Single-replica deploy → memory:// is correct for slowapi state.
RATE_LIMIT_STORAGE_URI=memory://
WEB_CONCURRENCY=2

# LOCAL_MODE seeds two demo accounts. Leave UNSET in production.
LOCAL_MODE=
```

Click **Deploy**. The container builds, the bootstrap module
runs Alembic to HEAD, and uvicorn serves both the API and the
SPA on ``https://opkomst.nu``. The Dockerfile ships a built-in
``HEALTHCHECK`` so Coolify's status indicator picks it up
automatically.

Verify cheap healthcheck: ``curl https://opkomst.nu/health``
returns ``{"status":"ok"}`` (Coolify pings this every 30 s — kept
constant-time on purpose). For the full introspection payload
(``schema_head``, ``oldest_pending_dispatch_age_seconds``,
``disk_free_gb``, ``email_executor_max_workers``, DB connectivity),
use ``curl https://opkomst.nu/health/full``.

## 6. Cron jobs

Coolify → application → **Scheduled Tasks**. Seven jobs, all
running ``uv run --no-dev python -m backend.cli`` against the
same image. Stagger the minutes so they don't all hit the DB at
once.

| Schedule       | Command                                                           | Purpose                                            |
|----------------|-------------------------------------------------------------------|----------------------------------------------------|
| `0 *  * * *`   | `uv run --no-dev python -m backend.cli dispatch reminder`         | Hourly reminder send                               |
| `0 *  * * *`   | `uv run --no-dev python -m backend.cli dispatch feedback`         | Hourly feedback send                               |
| `30 * * * *`   | `uv run --no-dev python -m backend.cli reap-partial`              | Mid-flight crash recovery                          |
| `0 3  * * *`   | `uv run --no-dev python -m backend.cli reap-expired`              | Daily: finalise expired dispatches + 7-day ciphertext backstop |
| `45 3 * * *`   | `uv run --no-dev python -m backend.cli reap-auth-tokens`          | Daily: prune expired login + registration magic-link rows |
| `0 9 * * 1`    | `uv run --no-dev python -m backend.cli pending-digest`            | Weekly Monday 09:00 UTC: email every admin a list of accounts awaiting approval |
| `0 4  * * *`   | `bash scripts/backup.sh`                                          | Daily: redacted DB dump (see step 7)               |

Each job exits non-zero on failure → Coolify surfaces it as an
alert, and Sentry captures the exception once step 9 is wired.
The CLI deliberately re-raises rather than swallowing, so one
tick's hiccup never silently masks a real bug.

## 7. Bootstrap admin

The very first completion matching ``BOOTSTRAP_ADMIN_EMAIL``
gets ``role=admin, is_approved=true``. Requires SMTP from step 3
to be live — the magic link goes out over the same TEM hop.

1. Open ``https://opkomst.nu/login``.
2. Enter the email you set as ``BOOTSTRAP_ADMIN_EMAIL``. Submit.
3. Check your inbox for the "finish setting up your account"
   link. Click.
4. Fill in your name on the next page. Submit.
5. You land on ``/events`` as an admin. Done.

If the magic link doesn't arrive, check the Scaleway TEM
dashboard for the outbound delivery status (sent / soft-bounce /
hard-bounce). Local-mode dev: ``EMAIL_BACKEND=console`` writes a
``urls=[...]`` log line you can copy from.

## 8. Backups

Step 6 already added ``bash scripts/backup.sh`` to cron. The
script:

* Pipes ``pg_dump`` through ``scripts/_backup_redact.py`` which
  NULLs ``Signup.encrypted_email`` at dump time. Privacy stance:
  encrypted addresses don't sit in cold storage. Trade-off: a
  restore loses the ability to send any pending feedback emails
  (24h shelf life anyway).
* Writes ``opkomst-<UTC-stamp>.sql.gz`` into ``$BACKUP_DIR``.
* Prunes files older than ``$RETENTION_DAYS``.

Make sure the cron host has ``pg_dump`` available and a writable
``BACKUP_DIR``. Coolify by default runs Scheduled Tasks inside
the application container — both apply.

**Verify once, manually:**

```bash
# Inside the app container:
bash scripts/backup.sh
ls -la $BACKUP_DIR
# Should see exactly one file. Sanity-check the redaction:
zgrep -c '\\\\x[0-9a-f]\\{8,\\}' $BACKUP_DIR/opkomst-*.sql.gz
# 0 matches expected (no bytea hex blobs anywhere).
```

**Quarterly: run the restore drill** to verify backups actually
restore. ``docs/runbook.md`` → "Backups" has the command.

## 9. Sentry

Free tier is more than enough for opkomst's scale.

1. Sign up at https://sentry.io. Create a project, select **Vue**
   (or **FastAPI** — either works; we set both).
2. **Settings → Client Keys (DSN)** → copy the DSN.
3. Coolify env: set both ``SENTRY_DSN`` and ``VITE_SENTRY_DSN``
   to the DSN. Redeploy.
4. **Alerts → Create Alert** → "An issue is first seen this
   week" → Action: send email to you.
5. **Crons** — no manual setup. Each cron run sends a
   ``capture_checkin`` start + finish, and the in-progress
   check-in carries a ``monitor_config`` (schedule + margin +
   max_runtime) that upserts the monitor on first run.
   ``backend/cli.py`` is the single source of truth; the five
   monitors that get created automatically:

   | Slug                                  | Schedule       | Margin |
   |---------------------------------------|----------------|--------|
   | `opkomst-cli-dispatch-reminder`       | `0 * * * *`    | 5 min  |
   | `opkomst-cli-dispatch-feedback`       | `0 * * * *`    | 5 min  |
   | `opkomst-cli-reap-partial`            | `30 * * * *`   | 5 min  |
   | `opkomst-cli-reap-expired`            | `0 3 * * *`    | 30 min |
   | `opkomst-cli-reap-auth-tokens`        | `45 3 * * *`   | 30 min |
   | `opkomst-cli-pending-digest`          | `0 9 * * 1`    | 60 min |

   After the first successful run of each cron the monitor
   appears in Sentry → **Crons** (or Insights → Crons,
   depending on UI version) and starts paging on missed
   schedule + margin windows. The ``migrate`` and ``seed-demo``
   subcommands deliberately do *not* send check-ins — neither
   is a scheduled cron.
6. **Sentry → Insights → Uptime** (or **Crons → Uptime**
   depending on UI version) → **Add Monitor**. Pure UI, no SDK
   side; Sentry uptime checks are independent of
   ``capture_checkin``.
   - URL: ``https://opkomst.nu/health/full`` — same target as
     UptimeRobot below for the same reason: ``/health/full`` runs
     ``SELECT 1`` and returns **HTTP 503** when the DB is
     unreachable, so a plain HTTP-status check catches it. Cheap
     ``/health`` always returns 200 even with a dead DB and is
     for Coolify's container healthcheck only.
   - Interval: 1 min if your plan allows; otherwise the default.
   - Failure threshold: 3 consecutive failures (avoids
     one-blip noise).
   - Alert rule: tie to the same email/Discord contacts as the
     issue alert in step 4.

   Why both Sentry Uptime *and* UptimeRobot in step 10? Different
   failure modes. UptimeRobot is independent and off-network — it
   catches "the whole VPS is dead, including Sentry". Sentry
   Uptime correlates failures with Sentry's exception + cron
   view, so a check failure shows you "the 500 that fired one
   minute earlier" in the same UI. Free Developer tier currently
   includes one uptime monitor; one is plenty for opkomst.

## 10. UptimeRobot (load-bearing — do this even if you skip Sentry)

This is the only channel that catches "the whole VPS is dead".
Free tier, 5-min interval, takes 3 minutes.

1. Sign up at https://uptimerobot.com (no credit card).
2. **+ Add Monitor → HTTP(s)**:
   - URL: ``https://opkomst.nu/health/full`` — must use ``/full``
     here, not the cheap ``/health``: only the full route runs
     ``SELECT 1`` and returns **HTTP 503** when the DB is
     unreachable. Cheap ``/health`` always returns 200 (for
     Coolify's container healthcheck) and would never trip an
     uptime alert on a degraded DB.
   - Monitoring interval: 5 minutes.
   - No keyword/advanced setup needed — UptimeRobot's free tier
     no longer includes keyword monitoring, and the 503-on-
     degraded design means a plain HTTP-status check is enough.
3. **Alert Contacts** → add your email + (optional) push to
   the UptimeRobot mobile app.
4. **Test**: Coolify → stop application → wait <5 min. Email
   should arrive. Restart Coolify.

## 11. Coolify notifications

Coolify → project settings → **Notifications**:

* Enable email or Discord webhook for:
  * Deploy failed
  * Container restarted unexpectedly
  * OOM killed

Catches crash loops between UptimeRobot's 5-min pings.

## 12. Final verification

Run through this in order:

```bash
# 1. App is up (introspection payload — cheap /health just
# returns {"status":"ok"} and is for Coolify, not humans)
curl -fsS https://opkomst.nu/health/full | jq .
# {"status":"ok","db_connectivity":true,"schema_head":"<rev>",...}

# 2. SMTP works (check your inbox after each)
# - submit a fresh email at /login
# - the "finish setting up your account" link should arrive within 30 sec
# - click through and submit a name → you should land on /events

# 3. Cron is firing
# Coolify → application → Scheduled Tasks → check the last-run
# column for each of the seven jobs. All should show <1h ago
# (or <24h for daily ones).

# 4. Sentry receives events
# Sentry UI → "Issues" should show 0 issues + 1 transaction
# entry for the dispatch crons, OR test by hitting an endpoint
# that throws (curl https://opkomst.nu/api/v1/auth/me without
# a token → 401, doesn't fire Sentry; instead force a 500
# during initial QA via a sandbox deploy).

# 5. Backups land — exec into the API container and check the
# Persistent Volume mount.
ls -la /app/data/backups/
# At least one file from the last 24h.

# 6. UptimeRobot is green
# Dashboard at https://uptimerobot.com → status "Up" for
# https://opkomst.nu/health/full.
```

## 13. Day-to-day

Once setup is complete, the system runs on its own:

* **Code changes** → push to ``main`` → Coolify auto-deploys.
* **CI** runs ruff, pyright, pytest (with coverage gate),
  schema-drift, migration idempotency, e2e on every PR.
* **Dependabot** opens grouped weekly PRs for uv, npm, and
  github-actions. Click green, merge.
* **Quarterly**: run the restore drill (``docs/runbook.md``).
* **When something breaks**: ``docs/runbook.md`` is the playbook.

---

# Operations

## Rate limiting

Opkomst uses ``slowapi`` for per-IP rate limits. The default
storage backend is in-process memory (``memory://``), which means
each replica counts independently — running ``N`` replicas would
multiply effective limits by ``N``.

**Decision: opkomst runs as a single API replica**, behind
Coolify's reverse proxy. Email volume + traffic make horizontal
scaling unnecessary at the foreseeable scale, and a single
replica keeps SlowAPI's defaults correct without operating a
separate Redis instance for rate-limit state alone.

If you ever need to scale to multiple replicas, set
``RATE_LIMIT_STORAGE_URI=redis://<host>:6379/0`` in the Coolify
env so the limiter shares a counter across instances. The
``Settings`` model already accepts the variable; no code change
required. Cron sweeps remain on a single host regardless, so
multi-replica still won't double-send any email.

## Rotating secrets

* **``JWT_SECRET``** — invalidates every existing session. Users
  get re-prompted to log in. No data loss.
* **``EMAIL_ENCRYPTION_KEY``** — invalidates every encrypted
  email blob currently in flight. Any signup whose email hasn't
  been decrypted yet (status: ``pending``) loses the ability to
  receive a feedback email; the worker will mark them ``failed``
  and wipe the blob. Plan rotation around an event boundary.

## Monitoring

``structlog`` lines hit stdout; Coolify aggregates them. With
``SENTRY_DSN`` set, all unhandled exceptions land in Sentry, and
each cron sends ``capture_checkin`` start + finish events
(step 9). PII is OFF (``send_default_pii=False``); structured
logs deliberately omit emails, display names, and IP addresses,
and a static greppable test
(``tests/test_privacy.py::test_logger_pii_kwargs_allowlist``)
keeps that invariant honest.

## Local production smoke

To exercise the production image without touching Coolify:

```bash
docker compose up --build
```

Brings up ``api`` (port 8000) + ``postgres`` using the same
image. Open ``http://localhost:8000`` for the SPA. To exercise
a sweep:

```bash
docker compose run --rm api python -m backend.cli dispatch reminder
```

Or, single-container API only (no DB):

```bash
docker build -t opkomst:latest .
docker run --rm -p 8000:8000 --env-file .env opkomst:latest
```

For *development* (Vite hot-reload + uvicorn ``--reload``), see
the README — that's a different mode and not what this doc
covers.
