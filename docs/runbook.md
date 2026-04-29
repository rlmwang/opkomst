# Runbook

Operational scenarios with concrete commands. Optimised for "it's
01:00 and something is wrong" — short, copy-paste, no prose.

## Monitoring & alerting

### How "guaranteed" alerting works

There is no single channel that guarantees alerting. Each
channel has a blind spot, and the way you get to "you'll
definitely hear within ~5 min" is by stacking three independent
ones so a coincident failure is implausible.

| failure mode | uptime monitor | Sentry exception alerts | Sentry cron monitors | Coolify alerts |
|---|---|---|---|---|
| API container died | ✅ within 5 min | ✗ (process gone) | depends | ✅ on restart attempt |
| Process running but throwing 500s | ✗ (`/health` still 200) | ✅ first event | ✗ | ✗ |
| Cron host died (jobs not running) | ✗ | ✗ | ✅ missed heartbeat | depends |
| DB unreachable | ✅ (`/health` returns `degraded`) | ✅ exception on next request | ✅ cron will fail | ✗ |
| Disk full | ✅ (`disk_free_gb` rule) | ✅ exception on next write | ✅ cron will fail | ✗ |
| Coolify itself is down | ✅ | depends | depends | ✗ (it's the thing that's down) |
| All of the above | UptimeRobot still pings | ✗ | ✗ | ✗ |

So the answer is: you're guaranteed alerts on every realistic
failure mode **as long as the uptime monitor is configured**.
The other two layers are how you find out *what* broke without
having to dig.

### Setup checklist (do once, ~15 min)

Tick these off in order. Until **#1** is done, you have no
guarantee.

#### 1. UptimeRobot (load-bearing — do this first)

- Sign up at https://uptimerobot.com (free tier, no card).
- Add Monitor → HTTP(s):
  - URL: `https://flatwork.nl/health`
  - Monitoring interval: 5 minutes (free plan minimum)
  - **Advanced → "Keyword Monitoring"**: keyword `"status":"ok"`,
    "Alert when keyword exists: NOT exists" — this catches the
    `degraded` case where DB is down but process is up.
- Alert Contacts → add your email + (optional) push to the
  UptimeRobot mobile app.
- Test by sending the API a deliberate 500: stop the container
  via Coolify; you should get an email within 5 min.

#### 2. Sentry — exception alerts

- Already wired in code via `SENTRY_DSN`. Confirm it's set in
  Coolify env: `echo $SENTRY_DSN | wc -c` returns >1 inside
  the running container.
- Sentry UI → project → Alerts → Create Alert → "An issue is
  first seen this week" → action: send email to you.
- Test by hitting an endpoint that throws (fastest:
  `curl https://flatwork.nl/api/v1/events/by-slug/<garbage>`
  returns 404, not 500 — instead force one with `gh issue` or
  a temporary throw in a sandbox deploy).

#### 3. Sentry — cron heartbeat monitors

`cli.py` sends `capture_checkin` for every invocation under
slugs `opkomst-cli-{cmd}`. Tells Sentry "I ran" so it can page
you when a job is missing.

- Sentry UI → Crons → Add Monitor for each cron slug:
  - `opkomst-cli-dispatch-reminder` — schedule `0 * * * *`,
    checkin-margin 5 min, max-runtime 10 min
  - `opkomst-cli-dispatch-feedback` — same
  - `opkomst-cli-reap-partial` — schedule `30 * * * *`
  - `opkomst-cli-reap-expired` — schedule `0 3 * * *`,
    checkin-margin 30 min
  - `opkomst-cli-reap-post-event-emails` — schedule `30 3 * * *`
  - `opkomst-cli-reap-login-tokens` — schedule `45 3 * * *`

#### 4. Coolify notifications

- Coolify project → Notifications → enable email (or Discord
  webhook) for:
  - Deploy failed
  - Container restarted (unexpected)
  - OOM killed
- Catches crash loops between UptimeRobot's 5-min pings.

### Why three layers

* **External uptime monitor** is the only thing that catches
  "the whole VPS is unreachable" — Sentry + Coolify both run
  *adjacent to* the failed container or rely on the container
  itself reporting in.
* **Sentry exception alerts** catch "the process is up and
  responding to `/health` but a real user request is throwing".
  The uptime monitor would be cheerfully green.
* **Sentry cron monitors** catch "the cron host died, no email
  has been sent in 6 hours". The uptime monitor still pings the
  API; nobody else notices the missing emails until your
  organisers do.

### Quick verification

Once configured, force a test alert on each channel:

```bash
# 1. Uptime monitor: stop the container, wait <5 min, expect email
docker compose stop api

# 2. Sentry exception: force a /health failure by stopping the DB
docker compose stop postgres
curl https://flatwork.nl/health | jq .status   # "degraded"

# 3. Sentry cron: skip a tick. Easiest is to disable one
#    Coolify cron job and wait for its checkin-margin window
#    to elapse — Sentry pages.
```

---

## "The email queue is stuck"

Symptom: `/health` reports `oldest_pending_dispatch_age_seconds`
above ~3600 (one cron tick).

```bash
# How many rows are pending per channel?
psql "$DATABASE_URL" -c "
  SELECT channel, COUNT(*)
  FROM signup_email_dispatches
  WHERE status = 'pending'
  GROUP BY channel;
"

# Try a manual sweep — exits non-zero on failure with a Sentry
# event captured.
docker compose exec api python -m backend.cli dispatch reminder
docker compose exec api python -m backend.cli dispatch feedback

# If the sweep itself ran cleanly but rows stay pending, the
# event-window predicate isn't matching. Check one row:
psql "$DATABASE_URL" -c "
  SELECT d.id, d.channel, d.created_at, e.starts_at, e.ends_at
  FROM signup_email_dispatches d
  JOIN signups s ON s.id = d.signup_id
  JOIN events e ON e.entity_id = s.event_id
  WHERE d.status = 'pending'
  ORDER BY d.created_at LIMIT 5;
"
```

A reminder dispatch whose event already started won't fire — the
reaper will mark it expired on the next daily tick.

## "A reminder fired twice"

Shouldn't happen — the conditional UPDATE filtered on
``status='pending'`` is the atomic claim. But if it does:

```bash
# Find the dispatch row + look at its message_ids
psql "$DATABASE_URL" -c "
  SELECT id, status, message_id, sent_at
  FROM signup_email_dispatches
  WHERE signup_id = '<signup-id>' AND channel = 'reminder';
"
```

Two rows with the same `(signup_id, channel)` would mean the
unique constraint `uq_dispatches_signup_channel` is missing or was
dropped — check the migration history. One row that flipped
`pending → sent → pending` would mean the conditional UPDATE
stopped working — file a bug.

## "A webhook keeps failing"

Symptom: Scaleway TEM dashboard shows webhook 401/503 spam.

```bash
# 503 means SCALEWAY_WEBHOOK_SECRET is unset on the server.
# 401 means a signature mismatch — Scaleway changed its signing
# scheme or the secret rotated on their side.
echo "$SCALEWAY_WEBHOOK_SECRET" | wc -c   # > 1 if set

# Inspect the most recent webhook attempt's request body to
# verify the signature manually:
echo -n "<raw body>" | openssl dgst -sha256 -hmac "$SCALEWAY_WEBHOOK_SECRET"
```

## "Restore from backup"

Use the restore drill to verify your backup before you need it
under pressure. Quarterly cadence:

```bash
BACKUP_DIR=/var/backups/opkomst \
  PGUSER=postgres PGPASSWORD=... \
  PGHOST=db.flatwork.nl PGPORT=5432 \
  ./scripts/restore_drill.sh
```

The script restores the latest dump into a temporary database,
runs migrations to HEAD, prints row counts, and drops the temp
DB. Non-zero exit means the backup didn't restore cleanly.

## "Encryption key rotation"

`EMAIL_ENCRYPTION_KEY` rotation is destructive — the AES-GCM key
is the only way to decrypt outstanding ciphertexts. Procedure:

1. **Drain the queue first.** Run dispatcher sweeps until
   `oldest_pending_dispatch_age_seconds` is null, then run
   `reap-post-event-emails` to wipe any lingering ciphertext.
2. Set the new `EMAIL_ENCRYPTION_KEY` in Coolify env. Deploy.
3. New signups encrypt under the new key from that moment.

If you have to rotate without draining, you'll lose the ability
to send any pending email — old ciphertexts are unreadable.

## "Schema head mismatch"

`/health` returns `schema_head: <some-rev>` while the deployed
code expects HEAD. Run migrations:

```bash
docker compose exec api uv run alembic -c backend/alembic.ini upgrade head
```

`cli.py` runs migrations on every cron tick, so a missed
migration usually self-heals within an hour. If it doesn't, the
migration itself is failing — check the cron log / Sentry.

## "Bounce rate too high"

Sentry warning: `high_bounce_rate event_id=... rate=0.18`.

Means ≥10% of finalised dispatches for one event bounced or
hit the spam folder. Either the venue's mailing list has stale
addresses, or you're tripping a reputation problem with Scaleway
TEM (rate-limit, IP block, etc).

Check the per-event breakdown:

```bash
psql "$DATABASE_URL" -c "
  SELECT status, COUNT(*) FROM signup_email_dispatches d
  JOIN signups s ON s.id = d.signup_id
  WHERE s.event_id = '<event-entity-id>'
  GROUP BY status;
"
```

A scattered handful of bounces is normal and the alert was
configured to require ≥5 finalised rows precisely so we don't
spam on those.
