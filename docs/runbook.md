# Runbook

Operational scenarios with concrete commands. Optimised for "it's
01:00 and something is wrong" — short, copy-paste, no prose.

## Monitoring & alerting (passive)

You should be alerted by **at least one** of three independent
channels for every production failure mode. None of them is
strictly redundant; each catches a class the others miss.

### 1. External uptime monitor — covers "the API is down"

**UptimeRobot** (free, 5-min interval) or **BetterStack** (free,
30-sec). Configure one HTTP monitor:

* URL: `https://flatwork.nl/health`
* Expect: status 200, body contains `"status":"ok"`
* Alert: email + push notification on first failure

Below 1 GB of disk free, ``/health`` reports `disk_free_gb` low —
add a "keyword on body" rule to alert when `"disk_free_gb"` is a
single-digit value.

### 2. Sentry — covers "something inside the running process threw"

Already wired (`sentry_sdk.init` in `main.py` and `cli.py`). In
the Sentry UI:

* **Alert rule**: Settings → Alerts → New Alert → "An issue is
  first seen" → email yourself.
* **Cron monitors**: `cli.py` sends `capture_checkin` for every
  invocation under monitor slugs `opkomst-cli-{cmd}` (one per
  subcommand). In the Sentry UI, Crons → Add Monitor for each
  slug, with an SLA matching the schedule (e.g. `0 * * * *` with
  a 5-minute checkin tolerance for hourly jobs). Sentry pages you
  if a heartbeat is missing.

### 3. Coolify container alerts — covers "the container restarts"

In Coolify project settings, enable email/Discord notifications
for:
* Deploy failures
* Container exited unexpectedly
* OOM kills

This catches crash loops between uptime-monitor pings.

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
