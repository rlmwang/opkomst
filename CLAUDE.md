# CLAUDE.md

## Rules

**#1 Rule: Always choose the cleanest design, not a shortcut. No backwards compat.** Every change should leave the codebase in a better state. We are pre-launch; never preserve old fields, shims, fallbacks, deprecated parameters, default values that exist "for legacy callers", transitional comments, or migration-time defensive checks. When you find code shaped by a previous version of itself, delete that shape — don't accommodate it. This rule applies to design docs and task specs too: do not write fix plans that step around old behaviour, audit-and-keep, or preserve any "before" state. Just write the right thing.

**#2 Rule: Never contradict the user's direct instructions.** When the user gives an explicit directive, implement it. Do not argue, defer, or propose alternatives unless asked. Do not claim work is done without actually testing it end-to-end.

## Privacy invariants

- **No PII in logs.** Routes log a single `INFO` line with a route name and outcome — no email, no IP, no User-Agent, no body content.
- **Email is decryptable only by the feedback worker.** No router endpoint may return a decrypted email. No admin tool may surface it. The decryption helper lives in `backend/services/encryption.py` and its only legitimate caller is `backend/services/feedback_worker.py`.
- **Encrypted email rows are deleted after use.** Successful or failed-after-retry, the column is nulled and the row's `feedback_sent_at` is set. We do not keep the ciphertext "just in case".
- **Open-source disclosure on the sign-up form.** The public event page must link to the repository and explain the data flow in one paragraph. Never remove that copy.
- **No third-party analytics or tracking pixels.** Ever.

## Project conventions

- **Models**: every model inherits `UUIDMixin` + `TimestampMixin` from `backend/mixins.py`. Never use auto-increment IDs.
- **Routes**: all live in `backend/routers/`, prefixed `/api/v1/`. Registered via `app.include_router(...)` in `backend/main.py`.
- **Schemas**: per-domain files in `backend/schemas/`. Email fields use the shared `LowercaseEmail` type from `backend/schemas/common.py` so user-identifying input is normalised at the boundary.
- **Auth**: JWT via `Authorization: Bearer`. Helpers in `backend/auth.py`. Two roles: `admin` > `organiser`. Unapproved organiser accounts can log in (so they can see the "awaiting approval" message) but cannot create events.
- **Migrations**: Alembic, auto-runs on startup. Generate with:
  ```bash
  uv run alembic -c backend/alembic.ini revision --autogenerate -m "description"
  ```
- **Encryption**: AES-GCM via `backend/services/encryption.py`. Key is `EMAIL_ENCRYPTION_KEY` (32 raw bytes, base64-encoded). Never assign defaults in code.
- **Slug generation**: 8-char nanoid via `backend/services/slug.py`. URL form: `/e/{slug}`.
- **Frontend**: Vue 3 Composition API + TypeScript + Pinia. Account-scoped data uses Pinia stores. PrimeVue 4 with `@layer primevue, app` cascade ordering — all global CSS goes inside `@layer app { }`.

## Documentation

- `docs/proposal/` — what we're building toward.
- `docs/current/` — what's in the codebase right now.
- `DESIGN_PLAN.md` — work queue.

## Commit style

Follow horeca-backend conventions: short subject, paragraph body explaining the why, `Co-Authored-By` trailer for AI assistance.
