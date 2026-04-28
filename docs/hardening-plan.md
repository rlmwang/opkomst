# Hardening & low-maintenance plan

The app is feature-complete. This plan refactors and tests every layer so
breakage surfaces fast and silent regressions become hard to introduce.
Maintenance burden falls when (1) every contract has a test, (2) every error
path is observed, (3) every change is reversible, and (4) every runtime
invariant is enforced at multiple layers.

Pre-launch: no backwards-compatibility shims. Every phase ships clean shape.

This plan is grounded in a full read of the codebase (73 backend Python files,
50 frontend Vue/TS files, 18 tests, 18 Alembic migrations, docker-compose,
Dockerfile, all docs). Concrete findings drive every item — every mitigation
is anchored to a file:line in the current tree.

---

## 0. Baseline (2026-04-28)

* Backend: **67 %** line coverage across 2 360 statements; 97 tests in 14 files.
* Frontend: **no automated coverage**; `vue-tsc` clean, `biome` clean.
* E2E: none (manual only).
* CI: nothing runs in CI today.
* Lint: ruff + pyright + biome + vue-tsc all clean locally.

### Coverage hot spots (≥40 % of statements unexercised)

| module | covered | gap |
|---|---|---|
| `services/email/smtp.py` | 0 % | live SMTP backend; never instantiated in tests |
| `backend/worker.py` | 0 % | scheduler entry-point; never instantiated in tests |
| `services/ics.py` | 17 % | calendar export; only one round-trip-ish path tested |
| `routers/feedback.py` | 22 % | `/{token}` GET, summary aggregations, submissions CSV, `email_health` per-channel |
| `seed.py` | 32 % | demo bootstrap (low priority — not on prod path) |
| `services/chapters.py` | 34 % | rename, restore, usage counts |
| `routers/chapters.py` | 43 % | DELETE + transfer flows, restore |
| `routers/admin.py` | 54 % | demote, delete, promote with self-target rejection |
| `routers/events.py` | 55 % | edit, archive, restore, ICS, QR, stats, send-now, both previews |

### Concrete findings from the audit (drive the rest of the plan)

* **`MESSAGE_ID_DOMAIN` is read on every `new_message_id()` call** (`services/email/identifiers.py:15`) but never validated at boot. If unset in prod, the first reminder mints `<…@None>` and Scaleway TEM rejects every send.
* **`SMTP_HOST` not validated at boot when `EMAIL_BACKEND=smtp`** (`services/email/backends.py:38–40`). The first send raises a `KeyError`; the worker's scheduled job swallows it and the next sweep re-tries forever.
* **Admin / chapter mutations have no rate limit** (`routers/admin.py`, `routers/chapters.py`). Only signup, send-now, register, login, feedback-submit are limited.
* **The webhook handler has no rate limit** (`routers/webhooks.py:60`) and relies entirely on HMAC. If `SCALEWAY_WEBHOOK_SECRET` is unset in prod the endpoint returns 503 to every request — recoverable, but a startup check would surface it loudly.
* **`SlowAPI` storage defaults to in-memory** (`services/rate_limit.py`, `RATE_LIMIT_STORAGE_URI=memory://` per `.env.example`). With 4 uvicorn workers the effective limit is 4× documented. Use Redis or pin to one replica.
* **Frontend `admin` store has no rollback on mutation failure** (`frontend/src/stores/admin.ts`). If approve / assign-chapter / promote / demote / delete fails server-side, the local users array drifts.
* **`_executor` max_workers=4 hardcoded** (`services/email/backends.py:55`). Not configurable.
* **Magic string `"__no_match__"` in chapter scoping** (`routers/events.py:62-64`, similar in `routers/feedback.py`). Reads as a 404 trick; clearer with `None`.
* **`architecture.md` is stale**: still says `Afdeling`/`feedback_email_status`/`feedback_worker.py + reminder_worker.py`. The Chapter rename, the dispatch-row normalisation, and the channel-parametric dispatcher are all unreflected.
* **`worker.py` has no graceful-shutdown timeout** (`worker.py:149–151`). `scheduler.shutdown(wait=True)` blocks SIGTERM until the in-flight send finishes; SMTP timeout is 10 s, but a stuck TLS handshake can block past Coolify's terminationGracePeriod.
* **No CI**: `pyproject.toml` defines tests + lint, but nothing runs them on push.
* **CSP allows `'unsafe-inline'` for styles** (`services/security_headers.py`) — required by PrimeVue 4's runtime CSS-in-JS. Re-audit when PrimeVue 4.x supports nonce-based CSP.
* **`scd2-safety` pre-commit check exists in CLAUDE.md prose but isn't installed**. Bare `db.query(SCDModel)` without a `valid_until IS NULL` filter is currently allowed.

---

## 1. Test scaffolding (do first — everything else depends on it)

**Goal:** every kind of test we'll need is reproducibly easy to write.

* **Split `tests/_worker_helpers.py`** into focused modules — currently the single helper file is 117 lines and mixes event/signup/dispatch concerns:
  * `tests/_helpers/events.py` — `make_event`, SCD2-aware variants
  * `tests/_helpers/signups.py` — `make_signup`, `get_dispatch`
  * `tests/_helpers/users.py` — `make_user_directly` (skip the auth-fixture chain when not relevant)
  * `tests/_helpers/chapters.py` — `make_chapter_directly`
  * `tests/_helpers/time.py` — re-export `clock`, `advance_to_next_sweep_tick(channel)`
  Goal: any test seeds an arbitrary world in 3–5 lines.
* **Centralise env isolation.** A single `_isolate_env` autouse fixture that resets `SCALEWAY_WEBHOOK_SECRET`, `EMAIL_BACKEND`, `EMAIL_BATCH_SIZE`, `EMAIL_RETRY_SLEEP_SECONDS`, `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS`, `MESSAGE_ID_DOMAIN`, `PUBLIC_BASE_URL`. Today `test_webhook_scaleway.py:42` does this ad-hoc; copy that pattern into a shared place.
* **Coverage gate.** Add `pytest-cov` to dev deps; make `pytest --cov=backend --cov-fail-under=70` part of the standard run. Raise the floor by 5 % at the end of every phase.
* **Hypothesis profile.** Today `test_timezone_invariants.py` runs 80 examples per test. Define a `ci` profile with `max_examples=20` for fast feedback, default to 80 locally.
* **Frontend test harness.** Wire **Vitest + @testing-library/vue + @vue/test-utils**. `frontend/src/__tests__/event-urls.test.ts` exists already (one test) — extend the convention. One smoke test per page module is the minimum.
* **End-to-end.** Wire **Playwright** for one happy-path per public flow: signup → reminder preview → feedback preview → submit. Currently zero E2E.
* **CI.** Add a GitHub Actions workflow running on every push:
  * `pytest` (with coverage gate)
  * `ruff check` + `pyright`
  * `biome check` + `vue-tsc`
  * `vitest`
  * `playwright test --project=chromium`
  * Same suite on Postgres (see § 7).

Acceptance: `make test` (or equivalent) runs backend + frontend + e2e and exits clean in <2 min.

---

## 2. Privacy & data-correctness lockdown

The app's core promise is "we delete your email after we're done with it." Every
breach of that promise must be caught at multiple layers.

### 2.1 Privacy invariants — encode + enforce at static + runtime + property level

Today (`tests/test_privacy.py:12`):
> `test_decrypt_only_called_from_email_dispatcher` proves only one call site reads ciphertext.

Extend:

* **Encrypt call sites.** `encryption.encrypt` is called once: `routers/signups.py:59`. Add a static test mirroring the decrypt one — fail if anything else imports `encryption.encrypt`.
* **`Signup.encrypted_email` writes.** Today the only writers are `routers/signups.py` (insert), `services/email_dispatcher.py` (NULL on wipe), `services/email_reaper.py` (NULL on wipe). Static AST scan: any other site is a privacy red flag.
* **State-matrix property test.** Hypothesis-fuzz random sequences of (signup, send, fail, retire, reap, webhook, post-event purge) operations against a small state machine. Final state always satisfies the wipe invariant: `encrypted_email IS NULL` iff no `pending` dispatch row remains.
* **Token expiry boundary.** `_resolve_token` (`routers/feedback.py:51`) compares naive datetimes. Add a test at the boundary minute around `FEEDBACK_TOKEN_TTL` (30 days) crossing DST.
* **Post-event purge probe.** The new daily purge (`email_reaper.purge_post_event_emails`) is tested. Add a *negative-path* probe: deliberately bypass every other wipe path (skip the wipe in dispatcher), advance clock 7 days, confirm the purge catches it. Proves the backstop works for *future* bugs.
* **`SCD2_employee_table`-style registry.** Out of scope — opkomst doesn't have employee restore; mention only to confirm we don't need it.

### 2.2 SCD2 correctness — port the `scd2-safety` rule

CLAUDE.md prescribes a pre-commit check that blocks bare `db.query(SCD2Model)` without `valid_until IS NULL` filter; this has not been installed in opkomst. Audit `git grep "db.query(Event)\|db.query(User)\|db.query(Chapter)"` — every call site must either use a helper (`scd2_svc.current(...)`, `scd2_svc.current_by_entity(...)`) or carry `# scd2-history-ok: <reason>`.

Confirmed call sites that need the audit:
* `routers/feedback.py:172, 305` (chapter-scoping the event lookup) — uses `scd2_svc.current(db.query(Event))` ✓
* `routers/events.py` (multiple) — mostly via helpers, audit each
* `services/chapters.py` — needs audit; 34 % coverage means much is untested

### 2.3 Email lifecycle — state-transition matrix

The dispatcher's state machine has 5 states (`pending`/`sent`/`failed`/`bounced`/`complaint`) and 4 transition triggers (worker tick, webhook, reaper, toggle-off). 5 × 4 = 20 (state, trigger) pairs. Today individual tests cover ~8.

Build a single table-driven test that enumerates each pair and asserts:
* allowed/disallowed transitions,
* idempotency under repeat,
* consistency with the wipe invariant.

This catches the kind of regression where a future change to one path silently breaks another.

---

## 3. Concurrency & idempotency

Worst failures involve races (two workers, worker + webhook, worker + organiser-edit).

* **Two-worker race tests.** `test_parallel_workers.py:21` covers REMINDER. Mirror for FEEDBACK; add a third test where two parallel sweeps cover *both* channels at once. Plus the toggle-off-during-send race in both directions.
* **Webhook + worker race.** Webhook arrives while worker has minted message_id but hasn't committed status. Test: end state consistent regardless of which side wins.
* **Reaper + worker race.** Reaper running concurrently with a sweep on the same event. Same property.
* **Migration idempotency.** Every Alembic `upgrade()` must be safe to run twice (data-only sections especially). The big backfill in `2b9a94e0632f` is the riskiest. Add a CI step that runs migrations top-to-bottom, then a second pass — must succeed cleanly.
* **Reaper idempotency.** Tested for `reap_partial_sends` and `reap_expired_windows`; extend explicitly to `retire_event_channels` and `purge_post_event_emails`.
* **Atomic-claim correctness.** The `WHERE status='pending' AND message_id IS NULL` claim relies on the `(signup_id, channel)` unique index (`models/email_dispatch.py:88`). Add a Hypothesis property: random interleaving of two transactions touching the same row never produces inconsistent state.

---

## 4. Time correctness

The reminder window, feedback delay, token TTL, and post-event purge are all
relative to wall-clock time. Naive vs aware datetimes are a recurring landmine.

* **Audit pass.** Every `datetime.now(`/`datetime.utcnow(`/`datetime(`/`timedelta` in backend. The audit found everything is currently `datetime.now(UTC)` — but assert this with a static test (grep for `datetime.utcnow` in `backend/`, fail if found).
* **Property test (already exists).** `tests/test_timezone_invariants.py` covers the reminder window. Extend to:
  * feedback delay (24h post-end) — same fuzz-and-compare-to-UTC-reference shape;
  * `FEEDBACK_TOKEN_TTL` redemption boundary;
  * `POST_EVENT_PURGE_DELAY` cutoff.
* **DST boundary cases.** Explicit cases at 2026-03-29 02:00 (NL DST start) and 2026-10-25 03:00 (DST end). All four time-windows must behave correctly across them.
* **Frozen-clock fixture coverage.** Today many tests use real time. The `clock` fixture (`tests/conftest.py:192`) exists; sweep tests until everything time-sensitive uses it.
* **Frontend.** `frontend/src/lib/format.ts` likely formats dates via `Intl.DateTimeFormat`. Add a Vitest test that locks the formatted output (`"dinsdag 30 april 2026"` vs `"Tuesday 30 April 2026"`) so a Node-version-driven Intl change can't silently flip the output.

---

## 5. Email deliverability + observability

Email is the only outbound side-effect. When it breaks, organisers don't know.

### 5.1 Webhook hardening

* **Rate-limit it.** Today `routers/webhooks.py:60` has no `@limiter.limit(...)` decorator. HMAC validates payload integrity but a leaked secret would allow unbounded "mark-as-bounced" requests. Add `@limiter.limit("60/minute")`.
* **Replay protection.** Same `(message_id, event_type)` posted twice should apply once. The `WHERE status='sent'` filter on the UPDATE (line 112) prevents downgrades; assert in tests that an already-bounced row stays bounced on a second `email_bounce` post.
* **Malformed JSON / unicode / oversized body fuzz.** `tests/test_webhook_scaleway.py` covers happy paths; add fuzz tests that always 204 / 401, never 500.
* **Provider-event coverage.** Scaleway TEM types we currently ignore (`email_delivered`, `email_open`, `email_click`, `email_dropped`, soft bounces) — `routers/webhooks.py:39-40` lists them. Document each policy decision in the test name (`test_email_open_never_changes_status`, etc.).

### 5.2 Sender hardening

* **Real SMTP tests.** `services/email/smtp.py` is 0 %. Add an integration test using `aiosmtpd` as a local fake SMTP server:
  * From / Message-ID / subject / body shape correct on the wire
  * Failure modes: connect refused, auth rejected, 421 transient, 5xx permanent
  * TLS handshake timeout (per-attempt)
* **Per-attempt timeout.** `send_email_sync` (`services/email/sender.py`) currently inherits the SMTP library default. A hung TLS handshake blocks a worker thread. Add an explicit timeout (5 s) and a test.
* **Suppression-list awareness.** Once a recipient bounces or complaints, future events shouldn't try the same address. Investigate whether Scaleway TEM does this server-side; if not, add an `email_suppressions` table populated from the webhook + checked at signup-time. Decide explicitly; document either way.
* **Bounce-rate metric per event.** Once an event's bounce rate crosses 10 %, log a `warning` so an organiser knows a list is rotting before the provider blocks.

### 5.3 Boot-time configuration validation

Add a fail-fast `validate_config()` called from both `main.py` and `worker.py` startup:

* Required regardless: `JWT_SECRET`, `EMAIL_ENCRYPTION_KEY` (+ length), `DATABASE_URL`, `CORS_ORIGINS`, `MESSAGE_ID_DOMAIN`, `PUBLIC_BASE_URL`.
* If `EMAIL_BACKEND=smtp`: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_PORT`.
* If `SENTRY_DSN` set: `SENTRY_ENVIRONMENT` must be one of `development`/`staging`/`production`.
* In prod (`SCALEWAY_WEBHOOK_SECRET=""` and `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS!=1`): warn loudly that the webhook will reject every request.
* `URL` shape checks: `PUBLIC_BASE_URL` parses, `CORS_ORIGINS` is comma-split URLs, etc.

The audit caught two specific risks here: `MESSAGE_ID_DOMAIN` is *required* per `services/email/identifiers.py:15` (`os.environ["MESSAGE_ID_DOMAIN"]`) but only fails on first send; `SMTP_HOST` is *only* required when `EMAIL_BACKEND=smtp` and only fails on first send.

### 5.4 Observability

* **`/health` completeness.** Currently `main.py:88` returns `email_executor_max_workers`. Add: schema head matches code (so a stale replica is visible), DB connectivity probe, dispatch lag (oldest-pending dispatch age across all events).
* **Structlog assertions.** For every important business event (`email_sent`, `email_bounced`, `signup_created`, `event_archived`, `feedback_submitted`, `auth_login_failed`), assert the log line is emitted with the expected structured fields. Today only `emit_metric` is asserted.
* **Sentry coverage.** The dispatcher captures retry-exhausted exceptions explicitly (`services/email/sender.py:108`). Audit other places where exceptions can fire on background threads — APScheduler swallows by default unless `EVENT_JOB_ERROR` is wired. Add a listener in `worker.py` that reports job errors to Sentry.
* **Metrics destination.** `emit_metric` writes to stdout; the deploy presumably scrapes it. Decide explicitly — keep stdout-as-metrics, or wire OpenTelemetry. Document the choice.

---

## 6. Public-surface security

Every public endpoint is a potential abuse vector.

### 6.1 Rate-limit coverage

Audit list (from § 0):

| endpoint | currently limited? | recommendation |
|---|---|---|
| `POST /auth/register` | 5/h | ✓ |
| `POST /auth/login` | 10/min | ✓ but consider IP-based fail2ban-style lockout |
| `POST /auth/verify-email` | none | add 30/h |
| `POST /auth/resend-verification` | none | add 5/h (else email-bomb vector) |
| `POST /events` | none | add 30/h (organiser only, but still bounded) |
| `PATCH /events/{id}` | none | add 60/h |
| `POST /events/{id}/archive` | none | add 30/h |
| `POST /events/{id}/restore` | none | add 30/h |
| `POST /events/{id}/send-emails/{channel}` | 5/h | ✓ |
| `POST /events/by-slug/{slug}/signups` | 30/h | ✓ |
| `GET /events/by-slug/{slug}` | none | add 120/min (cheap, but a determined attacker could probe slugs) |
| `GET /events/by-slug/{slug}/qr.png` | none | add 30/min (rendering cost) |
| `POST /admin/users/{id}/approve` | none | add 60/h |
| `POST /admin/users/{id}/promote` | none | add 60/h |
| `DELETE /admin/users/{id}` | none | add 30/h |
| every chapter mutation | none | add 30/h each |
| `POST /webhooks/scaleway-email` | none | add 60/min (HMAC is the gate, but bound CPU cost) |
| `POST /feedback/{token}/submit` | 20/h | ✓ |

### 6.2 SlowAPI storage

`memory://` per replica → 4 × per-pod limit. Either:
* run the API on a single replica (simpler for opkomst's scale), or
* set `RATE_LIMIT_STORAGE_URI=redis://…` in prod.
Document the deployed choice in `docs/deploy.md`.

### 6.3 CSP / headers / CSRF

* `services/security_headers.py` ships HSTS, nosniff, no-referrer, frame-ancestors none, CSP — ✓.
* CSP allows `'unsafe-inline'` for styles. PrimeVue 4 injects styles via `<style>` at runtime; nonce-based CSP requires PrimeVue support. **Re-evaluate annually**; nothing actionable today.
* No CSRF token. Stateless JWT in `Authorization: Bearer` is standard for SPA + API; safe as long as `Cookie` isn't ever used for auth. Document this decision.

### 6.4 Auth flow tests

Add explicit tests for: register → verify → admin approval → first login (bootstrap admin) → role change reflects in JWT after re-login → JWT expiry → invalid signature rejected. Some are tested; full matrix is missing.

`BOOTSTRAP_ADMIN_EMAIL` regression: add a test that registering twice with that email does **not** re-promote (already enforced by code; pin it with a test).

### 6.5 Public-event visibility

`GET /events/by-slug/{slug}` returns 404 when archived. Test. Same for the public signups endpoint and the email-preview endpoints (preview must 404 on archived events too — confirm and test).

---

## 7. Schema & migration safety

Postgres / SQLite parity is a recurring footgun.

* **CI matrix.** Run the full test suite on **both** SQLite and Postgres. Today SQLite only. The dispatch-table migration (`2b9a94e0632f`) is the highest-risk (Python-loop backfill); test it on Postgres explicitly.
* **Migration linter.** Pre-commit hook for every new migration:
  * uses dialect branching for FK / unique-constraint changes (template: `5928b093bf42`'s `_is_sqlite()`);
  * gives every constraint an explicit name;
  * has both `upgrade()` and `downgrade()` defined and reversible.
* **Schema-drift check.** `alembic check` on every PR — fails if the model diverges from the head migration.
* **Index coverage.** Audit `EXPLAIN`-like behaviour:
  * `Signup.event_id` — indexed (line 65 of models).
  * `SignupEmailDispatch (channel, status)` — indexed (`models/email_dispatch.py:96-99`).
  * `SignupEmailDispatch.message_id` — indexed (line 95).
  * `FeedbackToken.token` — PK.
  * `FeedbackResponse.event_id` — verify on Postgres (SQLite uses rowid).
  * `Event.slug` (current-version partial index) — verify the partial index is created on Postgres too (`events.py:50–58` uses both `sqlite_where` and `postgresql_where` — ✓).

---

## 8. Frontend data layer

Pinia stores have weaker contracts than backend code.

### 8.1 Mutation rollback

The audit caught: **`stores/admin.ts` does not roll back on mutation failure**. A failed `approve()` / `assign-chapter` / `promote()` / `demote()` / `remove()` leaves the local `users` array divergent from the server. Two options:

a. Add explicit rollback (snapshot the list before, restore on failure).
b. Always refetch after mutation — simpler, slightly slower.

For opkomst's scale, **(b) is fine**: refetch the users list inside the action's `catch`. Same review for `chapters.ts` and `events.ts` — they currently do optimistic mutations but no rollback.

### 8.2 Type safety

Audit `frontend/src/**/*.{vue,ts}` for `as ` casts. Each is a hole. Replace with proper type guards or schema-driven typing.

### 8.3 Stale data

`auth.ts` sets `loaded=true` even when `fetchMe()` fails (line ~94 per audit). This means "we don't know if you're logged in" presents as "you're logged out". Distinguish: `loadedAndAuthenticated` vs `loadedButFailed`; show a "couldn't reach server" banner when the second.

### 8.4 Coverage

Add Vitest tests for every store: action behaviour, computed getters, error propagation. Target 80 % per store.

### 8.5 E2E

One Playwright happy-path per public flow:
1. Anonymous signup → confirms the form persists draft → submits → thanks page.
2. Organiser register → admin approve → first event → public link → signup → reminder preview → feedback preview.
3. Webhook bounce arrives → email-health reflects it on the dashboard.

---

## 9. Operational reliability

Things that break in production.

* **Backup verification.** SQLite `opkomst.db` lives on the Coolify host volume. Document the backup cadence + a quarterly restore drill (script that downloads, restarts a sandbox, runs `/health`).
* **Migration rollback drill.** Pick one migration, run `alembic downgrade -1`, confirm app boots, restore. One-off exercise per release branch.
* **Disk-fill behaviour.** What happens when SQLite hits the disk limit? Current code surfaces a 5xx. Add a periodic disk-space probe in `/health`.
* **DNS / cert monitoring.** Cloudflare + Coolify-managed certs. Document the renewal mechanism + an alarm when `validUntil < 14d`.
* **Worker restart safety.** `worker.py:149-151` blocks SIGTERM until in-flight sends finish. Add a 30-s timeout on `scheduler.shutdown(wait=True)`; after that, log the stuck job and exit anyway. Test the kill-9 path explicitly with the partial-send reaper as the safety net.
* **Single-replica constraint.** APScheduler runs in `worker.py`. If `worker.py` runs on multiple replicas, every email fires N×. Document the constraint loudly; consider a leader-election lock (or stick with single replica for opkomst's scale).
* **`BOOTSTRAP_ADMIN_EMAIL`.** Document that this is a one-time bootstrap, that subsequent registrations with the same email do not re-promote (test pins this; document anyway).
* **Coolify env-var drift.** Build a `make verify-env` target that loads `.env.example` keys, compares to the running container's environ, fails if any required key is missing. Run as a deploy-time check.

---

## 10. Documentation

Stale docs are themselves a maintenance burden. The audit found three concrete drifts:

* **`docs/architecture.md`** — refers to "Afdeling" instead of "Chapter" (renamed in migration `5928b093bf42`); refers to `feedback_email_status`/`feedback_message_id`/`feedback_sent_at` columns (removed in `2b9a94e0632f`); refers to `feedback_worker.py + reminder_worker.py` (replaced by the channel-parametric `email_dispatcher.py` + `email_reaper.py`). **Rewrite.**
* **`README.md`** — keep user-facing only (per CLAUDE.md). Verify the run command (`uv run uvicorn …`) and the `PUBLIC_BASE_URL` guidance match the current dev workflow.
* **`docs/deploy.md`** — verify the API/worker split is documented end-to-end.

Add:

* **`docs/runbook.md`** — 5 short scenarios with concrete commands. No prose.
  * "the email queue is stuck"
  * "a reminder fired twice"
  * "a webhook keeps failing"
  * "encryption-key rotation"
  * "restore from backup"
* **`CLAUDE.md` for opkomst** — much smaller than horeca's, 30–60 lines: project identity, pre-launch rule, no SCD2 hard delete, the four reapers, the privacy invariant, env-var contract.

---

## 11. Dependency hygiene

* **`uv lock --upgrade`** monthly. Pin major versions of FastAPI / Pydantic / SQLAlchemy / APScheduler / cryptography. Run the test suite on every bump; commit the lockfile.
* **`npm-check-updates`** monthly. PrimeVue 4 minor bumps occasionally regress styles; visual review before merging.
* **Python EOL.** Running on 3.14. Calendar reminder for the EOL date.
* **Vuln scan.** `pip-audit` and `npm audit` in CI. Block merges on high-severity findings.
* **Pin runtime images.** `python:3.13-slim` and `node:22-alpine` in `Dockerfile` — pin to a specific digest, not the moving tag, to reproduce builds.

---

## 12. Small refactors caught by the audit

* **`services/email/backends.py:55`** — make `_executor` `max_workers` configurable via env (default 4).
* **`routers/events.py:62-64`** — replace the `"__no_match__"` magic string with `Event.chapter_id == None` + a separate branch.
* **`routers/feedback.py:62`** — same pattern, same fix.
* **`services/email_dispatcher.py:115`** — drop the defensive `or b""` around `signup.encrypted_email`. The query filter (`Signup.encrypted_email.is_not(None)`, line 235) already guarantees non-null. Decrypt failure is handled cleanly below.

---

## Phasing & sequencing

| phase | week | goal | deliverable |
|---|---|---|---|
| 1 | 1 | test scaffolding | `tests/_helpers/`, env fixture, coverage gate, Vitest + Playwright wired, CI green |
| 2 | 1 | privacy lockdown | static + property + transition-matrix tests, scd2-safety pre-commit |
| 3 | 2 | concurrency + idempotency | full race-test coverage, migration idempotency in CI |
| 4 | 2 | time correctness | full DST + tz property tests, frozen-clock everywhere |
| 5 | 3 | email + webhook hardening | aiosmtpd integration test, fuzzed webhook tests, `validate_config()` boot guard, /health expansion |
| 6 | 3 | public-surface audit | rate-limit coverage table, auth-flow tests, SlowAPI storage decision committed |
| 7 | 4 | postgres CI matrix | tests pass on both SQLite and Postgres |
| 8 | 4 | frontend coverage | Vitest at 80 %+, store-rollback fix, Playwright happy-path, `as ` cast audit |
| 9 | 5 | operational drills | backup/restore script, runbook, startup-check guards, dependency-vuln scan in CI |
| 10 | 5 | docs + small refactors | architecture/deploy/CLAUDE refresh, the four small refactors from § 12 |

Each phase ends with: tests passing, coverage ↑, CI green, one short status doc
in `docs/hardening-phase-N.md`. Don't start the next phase until the current
one's coverage gate is committed.

### Goal coverage by end

* Backend: **≥90 %** (statements + branches), with the few exempt modules (live SMTP — covered via integration test, demo seed) explicitly listed.
* Frontend: **≥80 %** Vitest coverage of stores + critical components.
* E2E: 1 happy path per public-facing flow (signup, feedback, reminder/feedback preview, organiser-edit, webhook).

---

## What this plan deliberately does **not** include

* New features.
* Performance optimisation (load is small; readability wins).
* Multi-tenancy.
* New email channels.
* Style / UX redesign.

If any of those become priorities later, treat them as separate plans with
their own phasing — do not interleave with hardening work.

---

## 13. Radical alternatives — collapse the bug surface, don't patch it

Sections 1–12 are incremental hardening: more tests, more guards, more docs.
Each fix patches a known leak. The deeper question is whether the *shape* of
the codebase is what's leaking.

The recent dispatcher refactor is the model: two ~230-line workers with 90 %
identical code, three parallel column sets on `Signup`, two webhook lookup
ladders — collapsed into one `ChannelSpec` table-driven loop, one normalised
dispatches table, one indexed query. **Adding a third channel now costs one
constant.** That's the kind of move that retires whole categories of bug at
once instead of testing harder against them.

The audit surfaced six more places where the same kind of move is on the
table. Each entry below estimates LoC delta and the **class of bug it makes
structurally impossible**, which is the only honest measure for a
low-maintenance app.

### 13.1 Postgres-only — drop SQLite entirely

**Current state.** SQLite for dev/test, Postgres in prod. The audit logged
multiple specific costs of the duality:

* Dialect branching in migrations (`5928b093bf42:_is_sqlite()`, future
  constraint-mod migrations require it everywhere).
* Naive UTC datetimes in SQLite, aware UTC at the boundary — every read does
  `replace(tzinfo=UTC)` somewhere (`routers/signups.py:48`,
  `routers/feedback.py:60`, the property test exists *because* of this).
* `native_enum=False` forced on every `SAEnum` column
  (`models/email_dispatch.py:74,78`).
* JSON columns behave subtly differently (`source_options`, `help_options`,
  `help_choices` — currently round-trip but a future Postgres-only feature
  like jsonb operators would diverge).
* The Python-loop backfill in `2b9a94e0632f` exists because SQLite can't do
  per-row id minting in pure SQL — Postgres can, with `gen_random_uuid()` or
  a generated column.
* Partial indexes need both `sqlite_where` and `postgresql_where`
  (`models/events.py:50–58`).

**Refactor.** Run Postgres locally via `docker compose up postgres` (already
in the deploy stack). Drop SQLite from `pyproject.toml` extras. Drop the
dialect branches. Move every datetime column to `TIMESTAMPTZ`. Remove every
`replace(tzinfo=UTC)`.

**Bug class eliminated:** the entire "naive datetime got compared to aware
datetime" family, every dialect-divergence migration bug, and the indirect
costs of writing every feature twice.

**Cost.** Medium. Local dev needs Postgres running. CI gets simpler (one
matrix entry, not two). Migration files lose ~15 % of their length.

**Recommendation: do it.** This is the single biggest reliability win
available. Phase it in week 7 instead of "make tests pass on both".

### 13.2 External cron, drop APScheduler

**Current state.** `worker.py` runs a `BackgroundScheduler` in-process. Three
scheduled jobs (one per channel sweep, plus the reaper). The whole worker
container exists for one reason: to host this scheduler. APScheduler swallows
job exceptions by default unless `EVENT_JOB_ERROR` is wired (it's not).

**Refactor.** Replace `worker.py` with three small entry-points:

```
python -m backend.dispatcher_tick reminder
python -m backend.dispatcher_tick feedback
python -m backend.reaper_tick
```

Each does one sweep and exits. Coolify cron (or the host's cron) invokes them
hourly / daily. Exceptions become exit codes; a non-zero exit becomes a
Coolify alert. Multi-replica safety becomes structural: only the cron host
fires. The `worker` Docker container goes away — the existing API image
already has everything needed.

**Bug class eliminated:** "scheduled job stopped firing because the scheduler
crashed silently"; "two replicas of the worker container fire every email
twice"; "SIGTERM during a sweep doesn't get observed cleanly". All four go
away.

**Cost.** Small. Coolify supports cron jobs natively. The `_safe_reap`
wrapper from § 5 of the audit becomes the cron entry-point. The
boot-time-reaper pattern stays (still runs at startup of the API replica, as
a defensive sweep).

**Recommendation: do it.** Replaces ~150 lines of `worker.py` +
`scheduler.add_job` + `_safe_reap` plumbing with ~30 lines of stand-alone
modules and one `coolify.yaml` cron stanza.

### 13.3 Magic-link auth — drop passwords entirely

**Current state.** Bcrypt with a 72-byte truncation quirk (`auth.py:25,29`).
No account lockout. Brute-force mitigated only by a 10/min rate limit. A
"forgot password" flow (not yet built — but it's coming if we keep
passwords). Plus the password column on the user model.

**Refactor.** Login becomes: enter your email → we send a magic-link token →
click → JWT issued. The token is a short-lived (15-min) signed value; the
existing `FeedbackToken` infra is the model. The `users.password_hash` column
goes away. The whole `bcrypt` dependency goes away.

The app already does email. The login UX for an organiser tool used a few
times a year is **better** with magic links than passwords ("which password
did I use here?").

**Bug class eliminated:** every "weak password" / "credential reuse" /
"account lockout policy" / "password reset email leaks token" concern. The
72-byte truncation. The bcrypt cost-factor decision. The "forgot password"
flow that doesn't exist yet but would have to be built and tested.

**Cost.** Medium. One migration to drop the password column. Update
`/auth/register` (no password field), `/auth/login` (email-only), add
`/auth/login-link` (token issuance). The existing `/auth/verify-email` flow
becomes redundant — registration *is* a verified email — and can be deleted.

**Recommendation: do it before launch.** Post-launch you have to migrate
existing passwords; pre-launch you just don't add the column.

### 13.4 OpenAPI-driven frontend types — single source of truth

**Current state.** Every frontend store hand-mirrors a Pydantic schema:

* `stores/events.ts:17` — `interface EventOut { id, slug, name, ... }`
  duplicates `schemas/events.py:47` `class EventOut`.
* `stores/feedback.ts:13` — same pattern for FeedbackForm.
* `stores/admin.ts` — same for AdminUserOut.
* When backend adds a field, frontend must remember to add it. Renames are
  worse — silent drift, no type error.

**Refactor.** `openapi-typescript` reads the FastAPI-generated `openapi.json`
and emits a `frontend/src/api/schema.ts`. `openapi-fetch` provides a typed
client (`api.get('/api/v1/events')` returns `EventOut[]` typed-from-schema).
The hand-written types in stores delete themselves.

**Bug class eliminated:** "frontend type drifted from backend schema". The
`as ` cast audit in § 8.2 evaporates because most casts existed to bridge
this gap.

**Cost.** Small. One `make generate-types` step in `package.json`; pre-commit
hook fails if the file is out of sync. About 200 lines of manual interfaces
deleted across the stores.

**Recommendation: do it.** Cheap and removes a whole category of silent drift.

### 13.5 Vue Query — retire the hand-rolled Pinia stores

**Current state.** Five Pinia stores (`auth`, `admin`, `chapters`, `events`,
`feedback`), totalling ~454 lines, all reinventing the same primitives:

* a list ref + `fetch()` populating it,
* `create()` / `update()` / `delete()` mutating local + remote,
* no rollback (`stores/admin.ts` is the worst — § 8.1).

The audit caught at least three places where a failed mutation diverges
local state from server state.

**Refactor.** Replace with `@tanstack/vue-query`:

* `useQuery({ queryKey: ['events'], queryFn: () => api.get('/api/v1/events') })`
  for reads — caching, refetching, stale-while-revalidate, all built-in.
* `useMutation({ mutationFn: …, onMutate: …, onError: … })` for writes —
  optimistic updates with **automatic rollback** on failure.

Auth state stays in a tiny Pinia store (it's session-state, not
server-state). Everything else goes through Vue Query.

**Bug class eliminated:** the entire "local store diverged from server after
a failed mutation" family. Stale data after window-focus changes. Manual
cache invalidation after mutations. Refetch-on-reconnect. Loading + error
state plumbing repeated five times.

**Cost.** Medium. ~454 lines of stores → ~200 lines of query hooks. New
dependency. Frontend smoke tests need updating.

**Recommendation: do it.** This is the frontend-side equivalent of the
dispatcher refactor: replacing five hand-rolled implementations of the same
pattern with one parametric library.

### 13.6 Pydantic Settings — single boot-time config validator

**Current state.** Env vars consumed at module-import and first-use across
the backend:

* `JWT_SECRET` (auth.py:14)
* `EMAIL_ENCRYPTION_KEY` (encryption.py:14, validates length here)
* `MESSAGE_ID_DOMAIN` (email/identifiers.py:15) — first send only
* `SMTP_HOST` (email/smtp.py:13) — first send only
* `PUBLIC_BASE_URL` (email/urls.py:11) — first send only
* `CORS_ORIGINS` (main.py:73) — at startup
* `SCALEWAY_WEBHOOK_SECRET` (webhooks.py:47) — first webhook only
* `EMAIL_BATCH_SIZE`, `EMAIL_RETRY_SLEEP_SECONDS`, `EMAIL_BACKEND`,
  `BOOTSTRAP_ADMIN_EMAIL`, `LOCAL_MODE`, `RATE_LIMIT_STORAGE_URI`,
  `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`,
  `WEB_CONCURRENCY`, `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS`.

15+ env vars. No central registry. The audit found two specific cases where
a misconfig fails on first use, not at boot.

**Refactor.** One `backend/config.py` with a single `Settings(BaseSettings)`:

```python
class Settings(BaseSettings):
    jwt_secret: SecretStr
    email_encryption_key: bytes  # validator: must be 32 bytes
    message_id_domain: str
    public_base_url: HttpUrl
    cors_origins: list[HttpUrl]
    email_backend: Literal["console", "smtp"] = "console"
    # … etc
    model_config = {"env_file": ".env"}

    @model_validator(mode="after")
    def smtp_required_when_smtp_backend(self):
        if self.email_backend == "smtp" and not self.smtp_host:
            raise ValueError("EMAIL_BACKEND=smtp requires SMTP_HOST")
        return self
```

Every `os.environ[…]` becomes `settings.jwt_secret`, etc. The settings
instance is loaded once at boot; missing/invalid env vars → app refuses to
start with a clear error pointing at the offending field.

**Bug class eliminated:** "deployment runs for hours before the first email
goes out, then we discover MESSAGE_ID_DOMAIN was unset." All env-var bugs
become startup-time failures.

**Cost.** Small-medium. ~30 sites to update. The audit's `validate_config()`
recommendation in § 5.3 *is* this refactor; doing it via Pydantic Settings is
the structural version, not just a defensive check.

**Recommendation: do it.** Cheap, prevents an entire category of "works on
my machine" deploy bugs.

### 13.7 Generic CRUD route helper — collapse the scope/archive/SCD2 dance

**Current state.** Every route that touches an event goes through:

```python
event = scd2_svc.current_by_entity(db, Event, entity_id)
if not event: 404
if user.chapter_id != event.chapter_id: 404
if event.archived_at is not None: 410  # or 404, varies
```

`routers/events.py:62-64` has the magic-string `"__no_match__"` workaround.
`routers/feedback.py` reimplements the same scope check. Half a dozen routes
inline the archive check inconsistently (some 410, some 404).

**Refactor.** One helper:

```python
def get_event_for_user(
    db: Session,
    entity_id: str,
    user: User,
    *,
    allow_archived: bool = False,
    public: bool = False,  # skip the chapter check
) -> Event:
    ...  # uniform 404 / 410 semantics
```

Same shape for users (`get_user_for_admin`) and chapters (`get_chapter_for_admin`).

**Bug class eliminated:** the "wait, is this route doing the archive check?"
audit. Every consistency mismatch between routes. The magic-string scope
workaround.

**Cost.** Small. ~12 call sites updated. The helper is ~15 lines.

**Recommendation: do it.** Makes the routers ~30 % shorter and forces
consistent semantics by construction.

### 13.8 Property-based testing as the primary test surface

**Current state.** Hypothesis is used in exactly one file
(`test_timezone_invariants.py`), 80 examples per test. Everywhere else the
tests are example-based: pick a scenario, assert outcome.

**Refactor.** Most invariants in this app are best tested as properties, not
examples:

* The privacy invariant (encrypted_email NULL iff no pending dispatch).
* The state-machine consistency under arbitrary trigger sequences.
* The wipe rule across DST boundaries.
* The atomic-claim under arbitrary interleaving.

Move from "tests assert behaviour on N hand-picked scenarios" to "tests
assert invariants hold over a generated state space". The
state-transition-matrix test in § 2.3 is example-based; the property version
generates a random sequence of triggers and asserts the invariants always
hold.

**Bug class eliminated:** the "we tested the cases we thought of" gap. The
"corner case nobody thought to write down" class.

**Cost.** Small. Hypothesis is already a dependency. Each property test is
shorter than the equivalent example matrix.

**Recommendation: do it.** Lower priority than 13.1–13.7 because it's a
testing-philosophy shift, not a structural refactor — but the lowest-cost
item on this list.

### 13.9 Considered and rejected

**Event sourcing for the dispatch state machine.** Instead of mutating a row
through 5 states, append events to a log; current state is a fold over
events. Genuinely powerful, but overkill for a sub-1000-events-per-day app.
The current state-machine + reapers is well-understood and the reapers
already handle the recoverability concern that event sourcing buys you.

**End-to-end privacy (recipient-key encryption).** Storing email encrypted
with a key only the recipient knows would mean the server literally can't
read the address. Lovely, but the recipient can't possibly hold a key when
they sign up — they don't even have an account. Not workable for this
threat model.

**`SQLModel` instead of separate Pydantic + SQLAlchemy.** The schemas and
the ORM models would unify, but `SQLModel` is still pre-1.0, has subtle
serialisation issues, and locks you into one ORM. Not worth the risk.

**Dropping Vue Router for file-based routing.** Cosmetic. Skip.

### 13.10 Recommended phasing of the radical refactors

If § 1–12 is a 5-week incremental hardening pass, this is a parallel **2-week
structural pass** that should happen *before* the hardening because hardening
the soon-to-be-deleted code is wasted work.

| week | refactor | ship-with |
|---|---|---|
| 1 | 13.1 Postgres-only | one PR; CI matrix dropped to single dialect |
| 1 | 13.6 Pydantic Settings | one PR; eliminates `validate_config` from § 5.3 |
| 1 | 13.4 OpenAPI types | one PR; eliminates the `as ` cast audit from § 8.2 |
| 2 | 13.2 External cron | one PR; deletes worker container |
| 2 | 13.7 Route helper | one PR; collapses the scope dance |
| 2 | 13.5 Vue Query | one PR; retires the manual stores |
| 3 | 13.3 Magic-link auth | one PR; drops bcrypt + password column |

13.8 (property-based tests) is best done *during* § 1–12, not as a separate
phase — every test added in § 2–4 should be a property when possible.

After this 3-week pass, the hardening work in § 1–12 has a much smaller
surface to cover. Total LoC reduction estimate:

| refactor | LoC delta |
|---|---|
| 13.1 Postgres-only | -100 (dialect branches, naive-datetime dance) |
| 13.2 External cron | -150 (worker.py + scheduler plumbing) |
| 13.3 Magic-link | -120 (bcrypt, password handling, password reset future-work) |
| 13.4 OpenAPI types | -200 (manual TS interfaces) |
| 13.5 Vue Query | -250 (Pinia store boilerplate) |
| 13.6 Pydantic Settings | -50 (scattered env var reads, +1 settings module) |
| 13.7 Route helper | -100 (per-route scope/archive checks) |
| **total** | **~-1 000 LoC** |

For an 11 600-line codebase, that's a **9 % reduction in the surface area
that has to be tested, reviewed, and maintained** — applied to the parts
where the most bugs lived. Net result is fewer lines, fewer dependencies,
fewer abstractions to keep in sync, and several whole categories of bug made
structurally impossible.
