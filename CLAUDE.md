# CLAUDE.md

## Rules

**#1 Rule: Always choose the cleanest design, not a shortcut. No backwards compat.** Every change should leave the codebase in a better state. We are pre-launch; never preserve old fields, shims, fallbacks, deprecated parameters, default values that exist "for legacy callers", transitional comments, or migration-time defensive checks. When you find code shaped by a previous version of itself, delete that shape — don't accommodate it. This rule applies to design docs and task specs too: do not write fix plans that step around old behaviour, audit-and-keep, or preserve any "before" state. Just write the right thing.

**#2 Rule: Never contradict the user's direct instructions.** When the user gives an explicit directive, implement it. Do not argue, defer, or propose alternatives unless asked. Do not claim work is done without actually testing it end-to-end.

## Project identity

Opkomst (`opkomst.nu`) is a privacy-first event sign-up tool for socialist organising. Attendees give a name (real or not), party size, and how they heard about the event. Optional email is encrypted at rest, used **once** to send a feedback form the day after the event, and then deleted. Everything in the codebase serves that contract.

## Privacy invariants

- **No PII in logs.** Routes log a route name + outcome only. Email-send is the only place `to=` ever appears.
- **Email decryption only by the lifecycle worker.** Static check: `tests/test_privacy.py::test_decrypt_only_called_from_mail_lifecycle` greps the backend tree for `encryption.decrypt` callers.
- **The wipe rule, asserted by the Hypothesis state machine** in `tests/test_privacy_invariant_property.py` and the table-test in `tests/test_email_state_machine.py`: ``Signup.encrypted_email IS NULL`` ⇔ no PENDING dispatch row pointing at this signup.
- **Encrypt write sites are an allowlist.** `tests/test_privacy.py::test_encrypted_email_writes_only_from_allowlisted_modules` keeps it tight.
- **Feedback responses carry no signup link.** No `signup_id` column on `FeedbackResponse`.
- **Open-source disclosure on every public sign-up form.** Never remove that copy.
- **No third-party analytics or tracking pixels.** Ever.

## Soft-delete

`User` and `Chapter` use a ``deleted_at`` column for soft-delete. ``Event`` uses ``archived_at`` for archive/restore. Edits overwrite in place; there's no version history (the audit log carries change records for admin-driven user mutations).

Conventions:

- Reads of live users/chapters filter `deleted_at IS NULL`.
- The ``users.email`` and ``chapters.name`` partial-unique indexes scope to ``deleted_at IS NULL``, so a soft-deleted email/name frees up its slot for a fresh registration. Re-registering an email un-deletes the existing row (clears ``deleted_at``, resets name+role+is_approved).
- **Multi-chapter membership** lives in ``user_chapters`` (composite PK ``(user_id, chapter_id)``, CASCADE on user/chapter hard-delete). Membership rows pointing at a soft-deleted chapter are preserved on disk so a chapter restore brings members back; reads filter on ``Chapter.deleted_at IS NULL`` everywhere — DTO projection, access scope, admin usage counts. Admins are global: ``access.chapter_ids_for_user`` returns every live chapter for ``role=admin``.
- ``Event.chapter_id`` is a real FK with ``ON DELETE SET NULL``. An event still belongs to exactly one chapter; the user's membership set must include it for the user to create or update the event.

## Auth

Magic-link only. No passwords, no bcrypt, no verify-email flow.

One door for both populations:

- `POST /auth/login-link` — accepts an email and always returns 200 (privacy: never reveal email existence). Branches by whether the email matches a live user:
  - Live user → mints a single-use 30-min `LoginToken`, sends `login.html` with a `/auth/redeem` link.
  - Unknown email → mints a single-use 30-min `RegistrationToken` keyed to the email (no `User` row yet), sends `register_complete.html` with a `/register/complete` link. A second `/login-link` for the same unknown email replaces the prior token, so only the most recent inbox link works.
- `POST /auth/login` — redeems a `LoginToken`, issues a JWT signed against `user.id`, deletes the token row.
- `POST /auth/complete-registration` — `{token, name}`; redeems a `RegistrationToken`, creates (or restores a soft-deleted) user, deletes the token row, returns the same `AuthResponse` shape as `/login` so completing sign-up is also the user's first sign-in.
- Bootstrap: the very first completion matching `BOOTSTRAP_ADMIN_EMAIL` lands as `role=admin, is_approved=true`. Race-safe via `IntegrityError` fallback on the partial-unique email index — concurrent completions or any concurrent live-user appearance leave the loser with 410.

Daily `python -m backend.cli reap-auth-tokens` deletes expired rows from both token tables.

## Conventions

- **No env defaults in code.** Every env var goes through `backend/config.py::Settings`. Required fields have no default. `Settings()` constructs at boot — fails fast on missing or malformed values.
- **All routes under `/api/v1/`**, in `backend/routers/`. Mutating endpoints (POST / PATCH / PUT / DELETE) carry a `@limiter.limit(...)` decorator; `tests/test_rate_limits_audit.py` enforces it.
- **All models inherit `UUIDMixin` + `TimestampMixin`.** No SCD2 layer; soft-delete via `deleted_at` (User, Chapter) or `archived_at` (Event).
- **Migrations:** every model change generates an Alembic migration. Initial schema is one fresh autogenerate (we're pre-launch; no production data to preserve). CI runs `alembic downgrade base ; upgrade head ; upgrade head` to pin idempotency.
- **Email writes go through `services/mail.py`.** Three entry points: `send_email` (fire-and-forget), `send_email_sync` (used by the lifecycle worker), `send_with_retry` (one retry + Sentry capture). Render, backends (console / SMTP / fake), Message-ID minting, metric emission, and the bounded thread executor all live in this one module.
- **Email lifecycle is channel-tagged.** `mail_lifecycle.run_once(channel)` and the four reapers handle both REMINDER and FEEDBACK. Per-channel deltas (window predicate, template name, context builder, feedback's token mint) are explicit `if channel == EmailChannel.REMINDER:` branches inside the module — adding a third channel adds a branch and a template, not a parallel code path.
- **Cron is one-shot.** `python -m backend.cli <subcommand>` invoked by Coolify scheduled tasks. Five subcommands: `dispatch reminder`, `dispatch feedback`, `reap-partial`, `reap-expired` (covers both expired-window cleanup and the 7-day post-event ciphertext backstop), `reap-auth-tokens` (login + registration tokens). No long-running scheduler container.
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
    mail.py                   render + send + retry + backends + observability
    mail_lifecycle.py         run_once(channel), run_for_event, reapers
    mail_templates/           Jinja templates ({nl,en}/*.html + base.html)
    encryption.py             AES-GCM encrypt/decrypt
    rate_limit.py             slowapi limiter shared across routers
    access.py                 chapter-scoped event lookup
    chapters.py               Chapter CRUD helpers
  alembic/                    one initial migration; CI pins idempotency

frontend/src/
  api/                        schema.ts (generated), types.ts, client.ts
  composables/                Vue Query queries + mutations (one per domain)
  stores/auth.ts              the only Pinia store
  pages/                      one page per route
  locales/                    i18n strings (nl + en)

tests/                        see docs/runbook.md for what each file proves

scripts/
  generate_openapi.py         dumps openapi.json from FastAPI app
  verify_env.py               pre-deploy env-var validator
  restore_drill.sh            quarterly restore-from-backup smoke
  backup.sh                   daily redacted pg_dump (encrypted_email NULL'd)

docs/
  architecture.md             current-state design
  deploy.md                   end-to-end go-live walkthrough + ops
  runbook.md                  monitoring + scenario playbooks
  principles-architecture.md  the rules the backend converges on, with where + why
  principles-ux.md            the rules the frontend converges on, with where + why
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
uv run python scripts/verify_env.py
```

## Commit style

Short subject, paragraph body explaining the why, `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer for AI assistance.
