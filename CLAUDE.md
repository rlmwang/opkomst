# CLAUDE.md

## Rules

**#1 Rule: Always choose the cleanest design, not a shortcut. No backwards compat.** Every change should leave the codebase in a better state. We are pre-launch; never preserve old fields, shims, fallbacks, deprecated parameters, default values that exist "for legacy callers", transitional comments, or migration-time defensive checks. When you find code shaped by a previous version of itself, delete that shape — don't accommodate it. This rule applies to design docs and task specs too: do not write fix plans that step around old behaviour, audit-and-keep, or preserve any "before" state. Just write the right thing.

**#2 Rule: Never contradict the user's direct instructions.** When the user gives an explicit directive, implement it. Do not argue, defer, or propose alternatives unless asked. Do not claim work is done without actually testing it end-to-end.

## Project identity

Opkomst (`opkomst.nu`) is a privacy-first event sign-up tool for socialist organising. Attendees give a name (real or not), party size, and how they heard about the event. Optional email is encrypted at rest, used **once** to send a feedback form the day after the event, and then deleted. Everything in the codebase serves that contract.

## Privacy invariants

- **No PII in logs.** Routes log a route name + outcome only. Email-send is the only place `to=` ever appears.
- **Email decryption only by the email dispatcher.** Static check: `tests/test_privacy.py::test_decrypt_only_called_from_email_dispatcher` greps the backend tree for `encryption.decrypt` callers.
- **The wipe rule, asserted by the Hypothesis state machine** in `tests/test_privacy_invariant_property.py` and the table-test in `tests/test_email_state_machine.py`: ``Signup.encrypted_email IS NULL`` ⇔ no PENDING dispatch row pointing at this signup.
- **Encrypt write sites are an allowlist.** `tests/test_privacy.py::test_encrypted_email_writes_only_from_allowlisted_modules` keeps it tight.
- **Feedback responses carry no signup link.** No `signup_id` column on `FeedbackResponse`.
- **Open-source disclosure on every public sign-up form.** Never remove that copy.
- **No third-party analytics or tracking pixels.** Ever.

## SCD2 query safety

Bare `db.query(<SCD2Model>)` without a current-version filter or a `# scd2-history-ok: …` comment fails `tests/test_scd2_safety.py`. Use the helpers in `backend/services/scd2.py`:

- `current(query)` — restrict to `valid_until IS NULL`.
- `current_by_entity(db, Model, entity_id)` — resolve entity_id → current row.
- `scd2_create / scd2_update / scd2_close / scd2_restore`.

`changed_by=None` on `scd2_create` self-references the new entity_id (the right shape for self-registration and seed rows; pass an explicit value when an authenticated actor created the row).

## Auth

Magic-link only. No passwords, no bcrypt, no verify-email flow.

- `POST /auth/login-link` — mints a single-use 30-min `LoginToken`, sends an email. Returns 200 either way (privacy: never reveal email existence).
- `POST /auth/register` — same shape; if the email already exists, mints a link to the existing account instead of 409'ing.
- `POST /auth/login` — redeems the token, issues a JWT signed against the user's stable `entity_id`, deletes the token row.
- Bootstrap: the very first registration matching `BOOTSTRAP_ADMIN_EMAIL` lands as `role=admin, is_approved=true`. Race-safe via `IntegrityError` fallback to the existing-email branch.

Daily `python -m backend.cli reap-login-tokens` deletes expired rows.

## Conventions

- **No env defaults in code.** Every env var goes through `backend/config.py::Settings`. Required fields have no default. `Settings()` constructs at boot — fails fast on missing or malformed values.
- **All routes under `/api/v1/`**, in `backend/routers/`. Mutating endpoints (POST / PATCH / PUT / DELETE) carry a `@limiter.limit(...)` decorator; `tests/test_rate_limits_audit.py` enforces it.
- **All models inherit `UUIDMixin` + `TimestampMixin`.** SCD2 dimensions also `SCD2Mixin`.
- **Migrations:** every model change generates an Alembic migration. Initial schema is one fresh autogenerate (we're pre-launch; no production data to preserve). CI runs `alembic downgrade base ; upgrade head ; upgrade head` to pin idempotency.
- **Email writes go through `services/email/sender.py`.** Three entry points: `send_email` (fire-and-forget), `send_email_sync` (used by dispatcher), `send_with_retry` (one retry + Sentry capture).
- **Email dispatch is channel-parametric.** One `email_dispatcher.run_once(spec)` function; per-channel behaviour lives in `ChannelSpec` instances in `services/email_channels.py`. Adding a new channel is a new `ChannelSpec` + a template, not a parallel code path.
- **Cron is one-shot.** `python -m backend.cli <subcommand>` invoked by Coolify scheduled tasks. Six subcommands: `dispatch reminder`, `dispatch feedback`, `reap-partial`, `reap-expired`, `reap-post-event-emails`, `reap-login-tokens`. No long-running scheduler container.
- **`LowercaseEmail`** at the schema boundary normalises identifying input (`backend/schemas/common.py`).
- **Slug generation**: 8-char nanoid via `backend/services/slug.py`. URL form: `/e/{slug}`.

## Frontend

- **Vue 3 Composition API + TypeScript + Vite + PrimeVue 4.**
- **State lives in TanStack Vue Query composables** (`frontend/src/composables/use*.ts`). The only Pinia store is `auth.ts`. Optimistic mutations carry an explicit `onMutate` snapshot + `onError` rollback so a failed write can't silently desync the cache from the server.
- **Types are auto-generated from the OpenAPI schema.** `make openapi` regenerates `openapi.json` + `frontend/src/api/schema.ts`. CI fails on drift.
- **PrimeVue 4 layer ordering**: all global CSS goes inside `@layer app { }`. `theme.css` declares `@layer primevue, app;` so PrimeVue's runtime-injected styles aren't trampled. Set up in `main.ts`.

## What's where

```
backend/
  config.py                   pydantic Settings, frozen, fail-fast
  cli.py                      one-shot cron entry-points
  auth.py                     JWT helpers + RBAC dependencies
  main.py                     FastAPI app, /health, SPA fallback
  models/                     one file per domain
  routers/                    one file per resource; @limiter on every mutator
  schemas/                    Pydantic DTOs (drives openapi.json)
  services/
    scd2.py                   create / update / close / restore helpers
    email_dispatcher.py       channel-parametric run_once(spec)
    email_channels.py         ChannelSpec instances (REMINDER, FEEDBACK)
    email_reaper.py           four reaper sweeps
    email/                    Jinja templates, console + SMTP backends
    encryption.py             AES-GCM encrypt/decrypt
    rate_limit.py             slowapi limiter shared across routers
    access.py                 SCD2-current + chapter-scoped event lookup
    chapters.py               Chapter SCD2 helpers
  alembic/                    one initial migration; CI pins idempotency

frontend/src/
  api/                        schema.ts (generated), types.ts, client.ts
  composables/                Vue Query queries + mutations (one per domain)
  stores/auth.ts              the only Pinia store
  pages/                      one page per route
  locales/                    i18n strings (nl + en)

tests/                        see docs/runbook.md for what each file proves

scripts/
  check_scd2_safety.sh        SCD2 query safety grepper
  generate_openapi.py         dumps openapi.json from FastAPI app
  verify_env.py               pre-deploy env-var validator
  restore_drill.sh            quarterly restore-from-backup smoke

docs/
  architecture.md             current-state design
  deploy.md                   Coolify setup, cron schedule, rate-limit storage
  runbook.md                  monitoring + scenario playbooks
  hardening-plan.md           original phase-A/B proposal
  execution-plan.md           the plan we're executing
```

## Running

```bash
set -a && source .env && set +a
make db-up
uv run uvicorn backend.main:app --reload
# in another terminal
cd frontend && npm run dev
```

`EMAIL_BACKEND=console` (the dev default) writes a structured `event=email_console` log line for every send with the `urls=[…]` field — that's how you grab a magic link in local mode.

## Useful commands

```bash
make db-up                  # postgres on :5433
make openapi                # regen openapi.json + frontend schema.ts
uv run pytest --no-cov      # full suite, skip coverage gate
uv run alembic -c backend/alembic.ini revision --autogenerate -m "msg"
bash scripts/check_scd2_safety.sh
uv run python scripts/verify_env.py
```

## Commit style

Short subject, paragraph body explaining the why, `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer for AI assistance.
