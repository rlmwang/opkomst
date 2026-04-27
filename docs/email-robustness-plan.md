# Email pipeline — improvement plan

Concrete, ordered work queue for hardening the reminder + feedback
email pipeline. Each task is self-contained: scope, files, and
acceptance criteria. Pick a task, do it, tick it off.

Status: `[ ]` pending · `[~]` in progress · `[x]` done.

---

## Phase 1 — Multi-worker safety (urgent)

The API container runs `uvicorn --workers 4`. APScheduler boots
inside every worker, so today every reminder and every feedback
email goes out four times. This phase fixes that.

### `[ ]` 1.1 Disable the scheduler in the API container

**Scope.** The API container should serve HTTP and only HTTP. The
scheduler runs in a dedicated sidecar.

**Files.**
- `Dockerfile` — set `ENV DISABLE_SCHEDULER=1` for the runtime
  stage so every uvicorn worker skips `_scheduler.start()`.
- `docker-compose.yml` (or Coolify equivalent) — add a `worker`
  service using the same image, override `CMD` to a new
  `python -m backend.worker` entrypoint that boots the scheduler
  loop without serving HTTP.
- New `backend/worker.py` — minimal entrypoint: import the
  schedulers, start them, block on `signal.pause()`, drain on
  SIGTERM. ~30 lines.

**Acceptance.**
- `docker compose up --scale api=4 worker=1` runs four API
  workers and one scheduler. Manually firing a reminder via
  the dev seed produces exactly one email, not four.
- Killing the worker container leaves API healthy.
- API container with `DISABLE_SCHEDULER=1` doesn't log
  `scheduler_started` on boot.

### `[ ]` 1.2 Pessimistic-lock status updates inside `_process_one`

Belt-and-braces against any future concurrency regression.

**Scope.** Both workers update the signup row only when its
status is still the value the worker observed at fetch time.

**Files.**
- `backend/services/feedback_worker.py:_process_one`
- `backend/services/reminder_worker.py:_process_one`

Replace direct attribute writes with a conditional UPDATE:

```python
updated = (
    db.query(Signup)
    .filter(Signup.id == signup.id, Signup.reminder_email_status == "pending")
    .update({...}, synchronize_session=False)
)
if updated == 0:
    logger.info("reminder_skipped_status_changed", signup_id=signup.id)
    return
```

**Acceptance.**
- Calling `run_once()` twice in parallel via
  `concurrent.futures.ThreadPoolExecutor` against the same DB
  produces zero duplicate sends (verified by the fake SMTP test
  in 5.4).

---

## Phase 2 — Idempotency + decrypt failures

### `[ ]` 2.1 Pre-mint message_id and persist before sending

**Why.** Today the worker generates a `message_id`, calls
`send_email_sync` (potentially blocking on SMTP), then commits.
A process kill between SMTP-ack and DB commit causes the next
tick to re-send.

**Scope.** Mint the message_id, write it to the signup row,
commit, *then* send. On worker boot, reap any signup whose
status is `pending` but whose `message_id` is set: those got
a partial send. Treat as `failed` (and log loud) rather than
risking a duplicate — humans can investigate the seven rows
this catches.

**Files.**
- `backend/services/feedback_worker.py`
- `backend/services/reminder_worker.py`
- New helper in `backend/services/email_lifecycle.py`:
  `reap_partial_sends(db)` that on boot scans both channels for
  rows with `status == "pending"` and `message_id IS NOT NULL`,
  flips them to `failed`, and logs.

**Acceptance.**
- A test that boots the worker, mints a message_id, asserts the
  row is committed, then crashes the SMTP send → verifies status
  remains `pending` with `message_id` set, then re-runs the
  worker after `reap_partial_sends` and verifies the row is now
  `failed` and won't be picked again.

### `[ ]` 2.2 Decrypt failure flips status to `failed`, doesn't retry

**Why.** `encryption.decrypt` raising means the ciphertext is
corrupt or the key changed. Neither has a recovery path. Today
we catch, log, return; the row stays `pending` and the worker
retries the same dead row every hour forever.

**Scope.** First decrypt failure → status `failed`,
`message_id = None`, ciphertext wiped via `wipe_if_done`. One
log line, no retry.

**Files.**
- `backend/services/feedback_worker.py:_process_one`
- `backend/services/reminder_worker.py:_process_one`

**Acceptance.**
- Test: insert a signup with garbage in `encrypted_email`. Run
  the worker. Assert status is `failed` after one tick. Run again,
  assert no second log entry / no second processing.

---

## Phase 3 — Catch-up + reaper

### `[ ]` 3.1 Reminders stuck `pending` after the window passes

**Why.** Reminder worker query is gated on `Event.starts_at >
now AND Event.starts_at <= now + 72h`. If the server is down for
the entire 72h window for some event, the row is never picked
up. It stays `pending` forever, ciphertext sits in the DB
indefinitely.

**Scope.** Daily catch-up job: `reminder_email_status == "pending"`
and `Event.starts_at < now` → flip to `not_applicable`,
`wipe_if_done`. Runs on the same scheduler as the workers.

**Files.**
- `backend/services/reminder_worker.py` — add `reap_expired()`.
- `backend/main.py` — register the daily job.

**Acceptance.**
- Test using `freezegun`: signup with `reminder_email_status=
  pending`, advance clock past the event start, run the reaper,
  assert status flipped + ciphertext wiped (if no other
  channel is pending).

### `[ ]` 3.2 Stuck `sending` rows (only relevant if 2.1 introduces a `sending` state)

If 2.1 keeps the binary `pending → sent/failed` model (as
proposed), this task is **not needed**. Mark complete by noting
"covered by 2.1's reap-partial-sends design".

---

## Phase 4 — Quotas + backoff

### `[ ]` 4.1 Per-tick batch limit

**Why.** A 5,000-signup event today drains the entire backlog
into one `run_once()` call. SMTP rate-limits trip and rows
flip to `failed` on transient errors.

**Scope.** Cap the per-tick batch at `EMAIL_BATCH_SIZE` (env,
default 200). Remaining rows are picked up next tick.

**Files.**
- Both worker `run_once()` queries: add `.limit(BATCH_SIZE)`.

**Acceptance.**
- Test: insert 500 pending rows, run the worker, assert exactly
  200 are processed. Run again, assert another 200. Run once
  more, assert the remaining 100.

### `[ ]` 4.2 Exponential backoff inside the two-attempt retry

**Files.**
- Both `_process_one`: replace `for attempt in range(2)` with a
  helper that sleeps 1s before attempt 2 (and gives up after).

**Acceptance.**
- Test that uses a fake backend raising `IOError` on first call,
  succeeding on second, and asserts the call timestamps are
  >= 1s apart.

### `[ ]` 4.3 Bound the email thread-pool

**Files.**
- `backend/services/email/__init__.py:get_executor` — set
  `max_workers=4` (or env-configurable).

**Acceptance.**
- Visible in `/health` or a debug endpoint that the executor's
  `_max_workers` is bounded.

---

## Phase 5 — Test infrastructure

This is where the durable value lives. Every robustness fix
above stays fixed only because a test catches the regression.

### `[ ]` 5.1 Fake email backend + fixture

**Scope.** A `services.email.testing.FakeBackend` that records
every `send` call (recipient, subject, message_id, body
substring matchers) and a pytest fixture that swaps
`get_backend()` to it for the duration of a test.

**Files.**
- New `backend/services/email/testing.py`.
- `tests/conftest.py` — fixture `fake_email`.

**Acceptance.**
- One smoke test that mounts the fixture, calls `send_email`
  directly, and asserts the captured email.

### `[ ]` 5.2 Frozen-clock fixture

**Scope.** A pytest fixture wrapping `freezegun.freeze_time`
parameterised by `tick_to(when: datetime)` so tests can advance
the clock and re-run workers.

**Files.**
- `tests/conftest.py`.
- `pyproject.toml` — add `freezegun` to the dev deps.

**Acceptance.**
- A test that freezes time, runs `reminder_worker.run_once()`,
  advances by 25 hours, and runs `feedback_worker.run_once()`,
  with the fake backend recording one of each.

### `[ ]` 5.3 Lifecycle helper unit tests

**Scope.** `services.email_lifecycle.wipe_if_done` is one
function with four cases:

| feedback | reminder | expected |
|----------|----------|----------|
| pending  | pending  | ciphertext kept |
| sent     | pending  | ciphertext kept |
| pending  | sent     | ciphertext kept |
| sent     | sent     | ciphertext wiped |

(With `failed` / `bounced` / `complaint` / `not_applicable` all
treated as "channel done" — also covered.)

**Files.**
- New `tests/test_email_lifecycle.py`.

**Acceptance.**
- Parametrised test covers the full matrix; one row per
  combination of {pending, not_applicable, sent, failed,
  bounced, complaint} for each of the two channels.

### `[ ]` 5.4 Worker behavioural tests

**Scope.** Cover the worker behaviours we already shipped + the
fixes from Phases 1-4.

**Files.**
- New `tests/test_reminder_worker.py`.
- New `tests/test_feedback_worker.py`.

**Required cases.**
- Reminder fires for an event 24h out, doesn't fire for an
  event 4 days out, doesn't fire for an event in the past.
- Feedback fires 24h after `ends_at`, doesn't fire if
  `questionnaire_enabled=False`.
- Reminder + feedback both fire on the same signup; ciphertext
  wiped after the *second* send, not the first.
- Reminder fires; organiser then disables feedback toggle;
  ciphertext wiped on the toggle-off, no second send needed.
- SMTP raises on every attempt → status `failed`,
  ciphertext wiped via lifecycle.
- Decrypt failure → status `failed`, no retry next tick (after
  Phase 2).
- Two parallel `run_once()` calls produce zero duplicate sends
  (after Phase 1.2).
- Per-tick batch caps at `EMAIL_BATCH_SIZE` (after Phase 4.1).
- Reaper flips expired-window reminders to `not_applicable`
  (after Phase 3.1).

**Acceptance.**
- Each bullet is one named test. CI green.

### `[ ]` 5.5 Webhook tests

**Scope.** Synthetic Scaleway TEM payloads against the
existing webhook router.

**Files.**
- New `tests/test_webhook_scaleway.py`.

**Required cases.**
- Bounce on a feedback message_id flips
  `feedback_email_status` to `bounced`.
- Bounce on a reminder message_id flips
  `reminder_email_status` to `bounced`.
- Unmatched message_id is logged but doesn't crash.
- Missing signature when secret is set → 401.
- Missing secret entirely → 503 (don't regress the audit fix).
- Opt-in `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS=1` → 204.
- Signature mismatch → 401.

**Acceptance.**
- All cases pass. No new lint warnings.

### `[ ]` 5.6 End-to-end signup-to-cleanup

**Scope.** Full lifecycle test using TestClient + fake backend
+ frozen clock.

**Required cases.**
- Public signup with email → advance to T-3d → reminder sent
  → advance to T+24h → feedback sent → ciphertext wiped at the
  feedback step, not before.
- Public signup with email → organiser flips both toggles off
  before reminder window → no email sent, ciphertext wiped
  immediately.
- Public signup *without* email → no ciphertext stored, no
  emails ever scheduled.
- Public signup with reminder-only event → reminder sent →
  ciphertext wiped at reminder step (no feedback to wait for).

**Files.**
- New `tests/test_email_lifecycle_e2e.py`.

**Acceptance.**
- All four scenarios pass; no flakes.

### `[ ]` 5.7 Time-zone property test

**Why.** `event.starts_at` round-trips naive ↔ tz-aware
through SQLAlchemy. The signup router re-attaches `tzinfo=UTC`
manually; the worker doesn't. Confirm both code paths agree on
"is this within 72h?" for a generated population of timestamps.

**Files.**
- New `tests/test_timezone_invariants.py` with `hypothesis`
  property tests.
- `pyproject.toml` — add `hypothesis` to dev deps.

**Acceptance.**
- Property test runs 1000 generated `starts_at` values and the
  worker's window check matches a hand-rolled reference.

---

## Phase 6 — Observability

### `[ ]` 6.1 Structured per-channel counters

**Scope.** Emit `email_sent_total{channel="reminder"}`-style
metrics. We don't have Prometheus today; add a structlog
"counter" event we can grep / pipe into log aggregation.

**Files.**
- Workers and webhook router.

**Acceptance.**
- Each send/failure/bounce produces a single
  `metric=email.{channel}.{outcome}` log line.

### `[ ]` 6.2 Sentry alerts on send-failure rate spikes

**Scope.** If we ever consistently see `*_send_failed` events,
fire a Sentry issue.

**Files.**
- `backend/services/email/__init__.py` or the workers — surface
  the exception to Sentry directly (the FastAPI integration only
  captures HTTP-served exceptions, not background-thread ones).

**Acceptance.**
- Manually trigger an SMTP failure → Sentry receives one event.

---

## Suggested execution order

1. **1.1 + 1.2** — close the live duplicate-send bug.
2. **5.1 + 5.2 + 5.3** — testing scaffolding before adding more
   behaviour, so the new fixes are born with coverage.
3. **5.4** — write the test cases for *current* behaviour first;
   they'll start failing in places the audit identified, which is
   the to-do list for the next group.
4. **2.1 + 2.2** — idempotency + decrypt-failure handling. Each
   gets its named test from 5.4 going green.
5. **3.1** — reaper. New test in 5.4.
6. **5.5 + 5.6 + 5.7** — fill out the test surface.
7. **4.1, 4.2, 4.3** — quotas + backoff.
8. **6.1 + 6.2** — observability.

## Effort estimate

| Phase | Effort | Risk if skipped |
|-------|--------|-----------------|
| 1     | 1.5h   | **High** — duplicate emails on every multi-worker deploy today |
| 2     | 3h     | Medium — rare but real duplicates / silent stuck rows |
| 3     | 1h     | Medium — privacy leak after long outage |
| 4     | 2h     | Low — only matters at scale |
| 5     | 6h     | High over time — without it everything regresses |
| 6     | 1h     | Low — but compounds with #5 |

Total: about a working day plus the test suite. The test suite is
the durable investment; everything else is local fixes.
