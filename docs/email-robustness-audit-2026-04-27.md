# Email infrastructure — robustness audit + plan

**Status: proposal.** Written 2026-04-27 immediately after the
reminder-email feature landed. This document maps the current
behaviour onto a list of failure modes, calls out where the system
quietly does the wrong thing, and proposes a phased plan to harden
it. Nothing here has been implemented yet.

## Current architecture (one-paragraph recap)

A signup with an email goes through up to two automated sends —
reminder (3 days before the event) and feedback (24h after). The
plaintext lives encrypted at rest (`Signup.encrypted_email`,
AES-GCM); the worker decrypts it once per send and the helper
`services.email_lifecycle.wipe_if_done` nulls the ciphertext as
soon as no channel is still `pending`. Two workers
(`reminder_worker`, `feedback_worker`) run hourly via APScheduler
inside the FastAPI process. Bounce/complaint feedback comes in
via `POST /api/v1/webhooks/scaleway-email`, matched on
`message_id`.

## What works

- **Crash mid-process**: APScheduler runs each tick on a fresh
  DB session, processes one signup at a time, and only commits
  at the end of each `_process_one`. Crashing mid-loop loses at
  most one signup's status update.
- **Worker shutdown**: `main.py` calls
  `_scheduler.shutdown(wait=True)` on lifespan exit, blocking
  until any in-flight send finishes. SIGTERM during deploy
  doesn't tear a signup mid-update.
- **Send failure (transient)**: `_process_one` retries each send
  twice in-process. Tolerates one flap.
- **Send failure (terminal)**: status moves to `failed`, the
  feedback `FeedbackToken` is dropped (no broken redemption
  link), ciphertext gets wiped per the lifecycle invariant.
- **Webhook fail-closed**: `SCALEWAY_WEBHOOK_SECRET` missing
  → 503 (audited and fixed earlier today). No blast-radius
  worry there.
- **Two channels share a clean privacy invariant**: ciphertext
  wiped only when both channels resolved (`email_lifecycle`
  centralises this; the workers and the toggle-off path all
  call into it).
- **Toggle-off is privacy-safe**: flipping a channel off in the
  event-edit form retires the corresponding pending statuses to
  `not_applicable` and wipes ciphertext if no other channel is
  still pending.

## What worries me

This is the actual audit. Each item is something I'd lose sleep
over if we shipped to production today.

### A. Server is down across a worker tick

Workers run in-process, hourly. If the server is down for the
hour the reminder window opens (or for several hours), no
catch-up happens beyond the next time the scheduler runs.

- **Reminder**: window is 72h wide, so a few hours' downtime is
  fine — next tick catches up. But if downtime spans the entire
  72h window (e.g. a misconfigured Coolify deploy left the
  container unhealthy for three days), every signup whose event
  starts inside that window misses its reminder. They stay
  `pending` *forever* because the worker query gates on
  `Event.starts_at > now`.
- **Feedback**: similar. The worker query gates only on
  `Event.ends_at <= cutoff` (=now-24h). There's no upper bound
  on `ends_at`, so an event that ended a year ago whose feedback
  never went out will still be picked up — *good* for catch-up,
  but means a long outage doesn't lose data.

So feedback self-heals; reminder doesn't. **Fix**: when the
reminder window passes without a send (event starts in the
past, signup status still `pending`), retire the row. Either
mark `not_applicable` ("we never sent it; address gets wiped on
the next opportunity") or treat it as `failed` so it shows up
on the organiser's failed-mail UI. I'd vote `not_applicable`
because there's nothing actionable.

### B. Multiple workers / concurrency

Today there's one scheduler in one process. The moment we run
more than one uvicorn worker that *also* enables APScheduler,
two reminder sweeps fight over the same row and we'd send the
reminder twice.

- The Dockerfile runs `uvicorn --workers 4`. But APScheduler
  only starts because `DISABLE_SCHEDULER != "1"`. Right now the
  Docker entrypoint doesn't set `DISABLE_SCHEDULER`, so **all
  four workers run the sweep**. Each picks up "pending" rows
  the moment their tick fires. Within one second each worker
  decrypts, sends, and updates the same signup four times.

This is the single most urgent bug in this section. **Fix**:

1. Short-term: set `DISABLE_SCHEDULER=1` in the Dockerfile and
   run a separate sidecar container (or a single dedicated
   worker process) that runs the sweep. Same code path; just
   don't enable it on the user-facing replicas.
2. Medium-term: move to a real queue. Two reasonable choices:
   - **Database-backed lock** (`SELECT … FOR UPDATE SKIP LOCKED`
     once we're on Postgres) — picks one row at a time, retries
     are idempotent because of the `pending` → `sent`/`failed`
     transition. Simple, no new infra.
   - **APScheduler with a single-instance external job store**
     (Postgres). One scheduler instance owns the trigger; any
     replica can execute. Slightly more setup but clean.

### C. Idempotency — what if a worker sends twice?

Today, every send mints a fresh `message_id` and the worker
flips the status to `sent` *after* the SMTP call returns. If
SMTP succeeds but the response gets lost (network hiccup, the
worker crashes between SMTP-ack and the DB commit), the next
tick re-sends. The recipient gets two reminders.

This isn't a hypothetical — `send_email_sync` is a thread call,
the DB commit happens after the loop. Process-kill in between
is a real window.

**Fix**:
- Move the status flip to *before* the SMTP call, with the row
  pre-stamped with `pending → sending` and a `sending_started_at`
  timestamp. Workers that crash leave a stuck row; a follow-up
  reaper retries `sending` rows older than (say) 30 minutes
  exactly once before flipping to `failed`.
- Or: trust the message_id. Pre-mint the message_id, write it
  to the row, then send. On worker restart, look at rows with
  `status=pending` and `message_id IS NOT NULL` — that's a
  partial send. Either accept the duplicate risk and re-send,
  or delete the row's `message_id`, treat the original as lost,
  and resend. (For our scale and use case, "send may go twice
  in extreme crash recovery" is acceptable; documenting it is
  what matters.)

### D. SMTP backend behaviour

The SMTP backend currently:
- Has no per-recipient quota. A single misconfigured event
  with 5,000 sign-ups all firing in the same hour would blast
  through Scaleway's per-minute send limits and start failing
  in a way that flips most rows to `failed`. We then never
  retry.
- Has no exponential backoff. The two retries are immediate.
- Holds plaintext in a thread pool task; no bound on
  concurrency. Today the pool is tiny so this isn't a real
  worry, but if we ever bump it we need to think about how
  many emails can be in flight before the DB session gets
  stale.

**Fix**:
- Cap concurrency on the executor (`max_workers=4` is fine).
- Pace sends: chunk the per-tick batch into small groups
  with sleep-between, or move to a proper rate-limit
  middleware around `send_email_sync`.
- Exponential backoff between the two retries (1s, 5s).

### E. Race between toggle-off and worker

Sequence:
1. Worker picks up signup S at tick T0.
2. Worker starts decrypting / sending.
3. In another request, organiser flips reminder OFF.
4. `_retire_disabled_channels` runs: `S.reminder_email_status`
   was `pending`, becomes `not_applicable`, ciphertext wiped if
   feedback also done.
5. Worker finishes, writes `S.reminder_email_status = "sent"` —
   overwriting the `not_applicable` we just set. Possibly with
   ciphertext already wiped, the worker's logic still reads
   the in-memory row.

Outcome: organiser sees `sent` despite having turned the
reminder off; recipient gets the email anyway. Privacy
contract leaks.

**Fix**: pessimistic-lock the row inside the worker during
`_process_one`, OR use a `WHERE` clause on the status update
("only flip to `sent` if status is still `pending`"). The
second is simpler.

### F. Decrypt fails silently

`encryption.decrypt` raises on bad ciphertext (e.g. wrong key,
corrupted blob). The worker catches the exception, logs it,
and… moves on with `plaintext=None`. The status stays `pending`
forever (the `if plaintext is not None` branch is the only
thing that flips it).

So a corrupted blob means the worker re-tries every hour for
eternity, logging an exception each time. No alert, no upper
bound.

**Fix**: count decrypt failures per signup (`reminder_decrypt_failures`
column or just stamp `failed` after the first decrypt
exception — there's no plausible recovery path from "ciphertext
won't decrypt"). I'd flip to `failed` immediately.

### G. The webhook is the only way bounces are recorded

If Scaleway never delivers a webhook (their outage, our endpoint
500s for a stretch, the secret was rotated and we missed it),
we never know. `Signup.feedback_email_status` stays `sent` for
emails that bounced into the void. No catch-up path.

**Fix**: this one is genuinely hard without a separate API call
to Scaleway to ask "what happened to message_id X". Acceptable
for now; document it as a known limitation. If it ever matters
we add a daily reconciliation job.

### H. Time-zone handling around the reminder window

`event.starts_at` is stored naive; we treat it as UTC. The
worker computes `now + REMINDER_WINDOW` and queries
`Event.starts_at <= deadline` against a naive column. As long
as everyone agrees on UTC this works.

But `signup_router.create_signup` reads `event.starts_at`,
finds it naive, and *manually* re-attaches `tzinfo=UTC` before
comparing. The worker doesn't — it compares a naive column
against a tz-aware `now + delta`. SQLAlchemy strips tz on
write but the comparison expression at query time… this needs
a real test.

**Fix**: pick one model — naive everywhere or aware everywhere
— and write a property test.

### I. Test coverage

There is *no* test for the two workers, the lifecycle helper,
or the toggle-off flow. The smoke tests we ran today were
hand-crafted in `python -c`. Every robustness item above is
silently regressible.

## Proposed plan (phased)

### Phase 1 — Make multi-worker safe (urgent)

1. Set `DISABLE_SCHEDULER=1` in Dockerfile for the API
   container.
2. Add a sidecar worker container in `docker-compose.yml` /
   Coolify config that runs the sweeps. Same image, different
   entrypoint that boots the scheduler without serving HTTP.
3. Add a status-update WHERE clause inside `_process_one`:
   ```python
   db.query(Signup).filter(
       Signup.id == signup.id,
       Signup.reminder_email_status == "pending",
   ).update(...)
   ```
   Belt-and-braces against any future concurrency bug.

### Phase 2 — Idempotency + decrypt failure

4. Pre-mint message_id, write to row, commit, *then* send.
   On startup, reap any row whose status is `pending` but whose
   message_id is set: heuristically those got a partial send;
   either resend (accept dup) or `failed` (accept loss). I'd
   pick `failed` and log loud — humans can investigate.
5. Decrypt failure → flip status to `failed` immediately.
   Stop the infinite-retry log spam.

### Phase 3 — Catch-up + reaper

6. Add a daily cleanup job: any `reminder_email_status=pending`
   for an event whose `starts_at` is in the past gets
   demoted to `not_applicable` and ciphertext wiped if no other
   channel pends. Runs on the same scheduler.
7. Same for stuck `sending` rows (if we adopt the explicit
   transition state in #4): older than 30 min → `failed`.

### Phase 4 — Quotas + backoff

8. Wrap `send_email_sync` with an exponential-backoff retry
   helper (1s → 5s → 25s, capped at 3 attempts).
9. Add a global concurrency limit on the email thread pool.
10. Per-tick batch size limit: don't drain 5,000 rows in one
    hour; pace at most 200/tick (configurable).

### Phase 5 — Test infrastructure

This is where most of the value compounds. None of the items
above stay fixed without tests.

11. **Unit tests for the lifecycle helper** —
    `email_lifecycle.wipe_if_done` is one function, four cases.
12. **Worker tests with a fake SMTP backend.** Mount a
    `services.email.testing.FakeBackend` that records every
    `send` call (subject, recipient, message_id, body match).
    Tests:
    - reminder fires for an event 24h out
    - reminder *does not* fire for an event 4 days out
    - reminder *does not* fire for an event in the past
    - feedback fires 24h after event ends
    - feedback *does not* fire if questionnaire toggle is off
    - reminder + feedback both fire and ciphertext is wiped
      after the *second* send, not the first
    - reminder fires, feedback toggle flips off, ciphertext
      gets wiped on the toggle event (no second send needed)
    - SMTP raises → status flips to `failed` after retries
13. **Property test for the time/timezone path.** Generate
    random `starts_at` values, fuzz the worker's window check
    against a hand-rolled "is this within 72h?" reference.
14. **Concurrency stress test.** Run two `run_once()` calls in
    parallel via `concurrent.futures` against the same DB; assert
    no signup ends in `sent` more than once and no row stays
    `pending` after both finish. Catches every regression in #3.
15. **Webhook tests** with synthetic Scaleway payloads — bounce
    flips status, complaint flips status, unmatched message_id
    is logged but doesn't crash.
16. **End-to-end through TestClient** with a fake SMTP that
    captures emails:
    - Public signup → reminder mail sent → feedback mail sent
      → ciphertext wiped at the right moment.
    - Public signup → toggle off → no mail sent, ciphertext
      wiped immediately.
17. **Fixture: per-test fresh DB + frozen clock.**
    `freezegun.freeze_time` lets us advance the clock and run
    `run_once()` to simulate days passing in milliseconds.

A reasonable target: every "What worries me" bullet above maps
to at least one named test case. Without that, the next refactor
silently breaks one of them.

### Phase 6 — Observability

18. Structured logs already do most of this. Add per-channel
    counters (sent / failed / bounced / complaint per hour) so
    we have a graphable signal that "the email pipe is alive".
19. Sentry alerts on
    `feedback_send_failed` / `reminder_send_failed` rate
    spiking. Would catch outages we'd otherwise discover when an
    organiser asks "where's my feedback?"

## Suggested order of work

1. Phase 1 (urgent — fixes a live bug if Docker enables more
   than one worker).
2. Phase 5 starts in parallel — write the tests for the *current*
   behaviour first, then evolve them as we patch.
3. Phase 2 — idempotency.
4. Phase 3 — catch-up.
5. Phase 4 + Phase 6 in any order; both are quality-of-life.

## Effort estimate (rough)

| Phase | Effort | Risk if skipped |
|-------|--------|-----------------|
| 1     | ~1h    | **High** — duplicate emails today on multi-worker deploy |
| 2     | ~3h    | Medium — duplicates / silent stuck rows |
| 3     | ~1h    | Medium — privacy leak on outage |
| 4     | ~2h    | Low — only matters at scale |
| 5     | ~6h    | High over time — without it everything regresses |
| 6     | ~1h    | Low — but compounds with #5 |

Total to "production-grade emailing": about a day of focused
work plus the test suite. The test suite is the durable
investment.
