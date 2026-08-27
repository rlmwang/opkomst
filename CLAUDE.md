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
- **No third-party scripts on organisation-branded pages.** Ever. No analytics or
  tracking pixels anywhere, on any page, in any brand. Advertising is the single
  exception to the first half: it runs on house-brand pages only (the root app and
  a personal account's public pages), behind a consent manager, and the CSP is
  loosened per response for those pages alone. Design in ``docs/ads.md``; not built yet.

## Tenants

Two kinds of tenant, one shape. An **organisation** is named in ``TENANTS`` with a brand folder committed for it; a **personal** tenant is one person who typed an address at the root, holds no chapters and no admin surface, and carries the ceilings in ``services/limits.py``. **Mail the app sends to
participants is the paid plan** (``Tenant.plan``, born from the kind):
reminders, feedback and chore reminders are refused on a free account and its
forms don't show the toggles, while sign-in, "here is what you made" and
approval mail are never gated. Design in ``docs/design-paywall.md``. Ask ``Tenant.is_personal``, never ``kind`` itself. **Every table carries ``tenant_id``** (NOT NULL, indexed) via ``TenantMixin``, denormalized onto child rows on purpose; ``tests/test_tenancy.py`` guards that it exists everywhere and that no child disagrees with its parent. Writes never name it — the column defaults to the tenant bound to the context (``services/tenancy.py``), bound by ``TenantBindingMiddleware`` from the JWT for organiser requests and by the resolved entity for public ones; nothing bound is an error, not a default. An organisation's app lives at ``/{tenant}/…``; the root is the personal app, and public URLs stay tenant-free. ``tenants.slug`` is an organisation's URL prefix and brand folder both; a personal tenant's slug is a generated id that never appears in a URL, and ``Tenant.brand_slug`` is what any page or email asks for the folder it wears. Full picture: ``docs/architecture.md``.

## Soft-delete

`User`, `Chapter` and `Tenant` use a ``deleted_at`` column for soft-delete. ``Event`` uses ``archived_at`` for archive/restore. Edits overwrite in place; there's no version history (the audit log carries change records for admin-driven user mutations).

Conventions:

- Reads of live users/chapters filter `deleted_at IS NULL`.
- The ``users.email`` and ``chapters.name`` partial-unique indexes scope to ``deleted_at IS NULL``, so a soft-deleted email/name frees up its slot for a fresh registration. Re-registering an email un-deletes the existing row (clears ``deleted_at``, resets name+role+is_approved).
- **Multi-chapter membership** lives in ``user_chapters`` (composite PK ``(user_id, chapter_id)``, CASCADE on user/chapter hard-delete). Membership rows pointing at a soft-deleted chapter are preserved on disk so a chapter restore brings members back; reads filter on ``Chapter.deleted_at IS NULL`` everywhere — DTO projection, access scope, admin usage counts. Admins are global: ``access.chapter_ids_for_user`` returns every live chapter for ``role=admin``.
- ``Event.chapter_id`` is a real FK with ``ON DELETE SET NULL``. In an organisation an event belongs to exactly one chapter and the user's membership set must include it to create or update the event; in a personal tenant there are no chapters, so it is null and a supplied one is a 422. Both rules live in ``access.assert_user_can_assign_chapter``.

## Auth

Magic-link only. No passwords, no bcrypt, no verify-email flow.

One door for both populations:

- `POST /auth/login-link` — accepts an email plus an optional `tenant`, and always returns 200 (privacy: never reveal email existence). With a tenant it is that organisation's door and branches by whether the email matches a live user in it:
  - Live user → mints a single-use 30-min `LoginToken`, sends `login.html` with a `/auth/redeem` link.
  - Unknown email → mints a single-use 30-min `RegistrationToken` keyed to the email (no `User` row yet), sends `register_complete.html` with a `/register/complete` link. A second `/login-link` for the same unknown email replaces the prior token, so only the most recent inbox link works.
  - Without a tenant it is the root's door: the address resolves to its personal account, or becomes one (`tenants.resolve_personal`), and always gets a `LoginToken`. No registration step, because there is nobody to approve you.
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
- **Organisations come from the environment**: `TENANTS=rsp:RSP,rood:ROOD`, reconciled into the `tenants` table by the CLI preamble on every boot (`services/tenants.sync_from_env`). Each slug needs a committed `brands/{slug}/`; dropping a slug soft-deletes that tenant. No UI, no platform-admin role.

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

brands/rsp/                   one folder per organisation: brand.json,
                              tokens.css (the palette), logo + icons.
                              Served at /brand/{tenant}/, injected into
                              every page head, never bundled.

tests/                        see docs/runbook.md for what each file proves

scripts/
  check_brand_tokens.py       no colour or logo outside brands/
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
