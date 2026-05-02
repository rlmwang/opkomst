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
| DB unreachable | ✅ (`/health/full` returns `degraded`) | ✅ exception on next request | ✅ cron will fail | ✗ |
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
  - URL: `https://opkomst.nu/health/full` — must be `/full`, not
    the cheap `/health`. Only the full route runs `SELECT 1` and
    returns **HTTP 503** when the DB is unreachable. Cheap
    `/health` always returns 200 (for Coolify's container
    healthcheck) and would never trip an uptime alert on a
    degraded DB.
  - Monitoring interval: 5 minutes (free plan minimum)
  - No keyword setup — UptimeRobot's free tier no longer offers
    keyword monitoring, and the 503-on-degraded design means a
    plain HTTP-status check is enough.
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
  `curl https://opkomst.nu/api/v1/events/by-slug/<garbage>`
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
    checkin-margin 30 min (also handles the 7-day post-event
    ciphertext backstop for the FEEDBACK channel)
  - `opkomst-cli-reap-auth-tokens` — schedule `45 3 * * *`
    (login + registration tokens; replaced
    `opkomst-cli-reap-login-tokens` — see deploy notes if upgrading)
  - `opkomst-cli-pending-digest` — schedule `0 9 * * 1`
    (Monday 09:00 UTC; emails every admin a list of accounts
    awaiting approval, skipped silently when there are none)

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

# 2. Sentry exception: force a /health/full failure by stopping the DB
docker compose stop postgres
curl https://opkomst.nu/health/full | jq .status   # "degraded"

# 3. Sentry cron: skip a tick. Easiest is to disable one
#    Coolify cron job and wait for its checkin-margin window
#    to elapse — Sentry pages.
```

---

## "The email queue is stuck"

Symptom: `/health/full` reports `oldest_pending_dispatch_age_seconds`
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
  JOIN events e ON e.id = s.event_id
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

## Backups

Daily ``scripts/backup.sh`` runs from cron at 04:00 UTC. It pipes
``pg_dump`` through ``scripts/_backup_redact.py`` which NULLs
``Signup.encrypted_email`` at dump time — even though the column
is AES-GCM ciphertext, the privacy stance is "addresses don't
sit in cold storage". Trade-off: a restore loses the ability to
send any pending feedback emails. Acceptable; those have a 24h
shelf life anyway.

Output: ``$BACKUP_DIR/opkomst-<UTC-stamp>.sql.gz`` (default
``/app/data/backups`` — the Coolify Persistent Volume mount inside
the container). Files older than ``$RETENTION_DAYS``
(default 30) are pruned at the end of each run.

The wrapper aborts the backup if the redactor didn't emit its
``-- opkomst-redacted: signups`` marker — that catches the
"schema rename made the redactor pass through unchanged"
failure mode loudly.

To verify a backup actually restores, run the drill (quarterly):

```bash
BACKUP_DIR=/app/data/backups \
  PGUSER=postgres PGPASSWORD=... \
  PGHOST=db.opkomst.nu PGPORT=5432 \
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
   `reap-expired` to wipe any lingering ciphertext (its
   FEEDBACK branch enforces the 7-day post-event backstop).
2. Set the new `EMAIL_ENCRYPTION_KEY` in Coolify env. Deploy.
3. New signups encrypt under the new key from that moment.

If you have to rotate without draining, you'll lose the ability
to send any pending email — old ciphertexts are unreadable.

## "Schema head mismatch"

`/health/full` returns `schema_head: <some-rev>` while the deployed
code expects HEAD. Run migrations:

```bash
docker compose exec api uv run alembic -c backend/alembic.ini upgrade head
```

`cli.py` runs migrations on every cron tick, so a missed
migration usually self-heals within an hour. If it doesn't, the
migration itself is failing — check the cron log / Sentry.

## "Reputation issues with the SMTP provider"

Opkomst doesn't ingest webhook delivery feedback (we used to;
Scaleway TEM moved its webhooks behind a paid Cockpit topic and
we pulled the integration). The SMTP provider's own dashboard is
the source of truth for bounce / complaint rates and reputation
warnings — check there if mail starts disappearing.
