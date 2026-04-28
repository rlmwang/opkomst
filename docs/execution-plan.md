# Execution plan — radical refactors + hardening

**Companion to `hardening-plan.md`**. That document is the audit + rationale.
This one is the day-by-day. Every entry below is a single PR with a clear
contract: what files change, what tests pass, what deploys.

Two phases. Phase A (3 weeks) is the structural pass: seven refactors that
collapse whole classes of bug. Phase B (5 weeks) is the hardening pass on
the smaller post-A surface. Phase 0 (week 1) is foundation work that both
phases depend on.

> Pre-launch convention: **no back-compat shims**. Every PR ships clean
> shape; no two-step migrations; no feature flags. Stack the PRs in order;
> don't merge a half-state.

---

## 0. Sequencing

### Critical path

```
0.1 ─┬─ A1 ─┬─ A2 ─┬─ A4 ─┬─ A7 ──── B1..B8
     │      │      │      │
     ├─ A3 ─┴──────┴──────┘
     │
     └─ A5 ─── A6
```

### Parallelism

* **0.1** (CI scaffolding) blocks everything.
* **A1** (Postgres-only) blocks **A2** because Settings can drop SQLite-only branches.
* **A3** (OpenAPI types) is independent — start in parallel with A1.
* **A4** (external cron) needs A2 (the cron entry-points read Settings).
* **A5** (route helper) is independent of everything; do it any time after 0.1.
* **A6** (Vue Query) needs A3 (the typed client).
* **A7** (magic-link) needs A2 (Settings owns JWT_SECRET) and A4 (cron sends the link emails — although the dispatcher already does, A4 just makes it cron-driven).

### Effort key

* **S** = ≤4 hours
* **M** = 1 day
* **L** = 2–3 days

---

## Phase 0 — Foundation (week 1)

Prerequisite for every other PR. CI runs the existing tests, coverage gate
locks in current 67 %, frontend test infra wired.

### 0.1  GitHub Actions CI for the existing test suite — **M**

Files: `.github/workflows/ci.yml` (new), `pyproject.toml` (add `pytest-cov`).

Tests: existing 97 backend tests + ruff + pyright + biome + vue-tsc all run on push.

Deploy: nothing.

Acceptance: a green CI badge on the next push; a failing test or lint blocks merge.

```yaml
# sketch
jobs:
  backend:
    steps:
      - uses: actions/setup-python@v5  # 3.13
      - run: uv sync
      - run: uv run pytest --cov=backend --cov-fail-under=67
      - run: uv run ruff check backend tests
      - run: uv run pyright backend
  frontend:
    steps:
      - uses: actions/setup-node@v4   # 22
      - run: npm ci
      - run: npx vue-tsc --noEmit
      - run: npx biome check
```

### 0.2  Split `tests/_worker_helpers.py` — **S**

Files: delete `tests/_worker_helpers.py`; add `tests/_helpers/{__init__.py,events.py,signups.py,users.py,chapters.py,time.py}`.

Tests: every test file's import line updated; suite still 97/97 passing.

Acceptance: `git grep "_worker_helpers"` returns 0 hits.

### 0.3  Centralise env isolation in a fixture — **S**

Files: `tests/conftest.py`.

Tests: drop the ad-hoc `monkeypatch.delenv` blocks in
`tests/test_webhook_scaleway.py:42` and elsewhere.

Acceptance: per-test env state is reset by the autouse fixture; suite still
green.

### 0.4  Wire Vitest + one smoke test — **M**

Files: `frontend/package.json` (deps), `frontend/vitest.config.ts` (new),
`frontend/src/__tests__/` (extend the existing `event-urls.test.ts`).

Tests: at least one Vitest test per Pinia store (smoke: imports + a single
assertion).

Acceptance: `npm run test` exits 0; CI runs it.

### 0.5  Wire Playwright with one happy-path — **M**

Files: `playwright.config.ts` (new), `e2e/signup.spec.ts` (new).

Tests: a public anonymous signup flow: open the public event page, fill
form, submit, see the thanks page.

Acceptance: `npx playwright test` exits 0 against `npm run preview`-served
build.

---

## Phase A — Structural pass (weeks 1–3)

### A1 — Postgres-only

Drop SQLite. Eliminates the dialect-branching tax on every future
migration; lets every datetime column be `TIMESTAMPTZ`; uses native enums.

Estimate: 1 week, single contributor.

#### A1.1  Bring up Postgres in `docker-compose.yml` and dev workflow — **S**

Files: `docker-compose.yml` (add `postgres` service), `.env.example`
(`DATABASE_URL=postgresql+psycopg://opkomst:opkomst@localhost:5432/opkomst`),
`Makefile` (new — `make db-up`, `make db-down`, `make db-reset`),
`README.md` (run command updated).

Tests: nothing yet.

Deploy: dev requires `docker compose up postgres` before `uv run uvicorn …`.

Acceptance: `make db-up && uv run alembic upgrade head` succeeds.

#### A1.2  Switch the test suite to a per-session Postgres database — **M**

Files: `tests/conftest.py`. Replace the per-process tempfile SQLite with a
testcontainer-style Postgres (or session-scoped docker container; or
expectation-of-running Postgres).

Strategy: `testcontainers-python` spins up a container per session;
schema-per-test isolation via `CREATE SCHEMA test_<id>` + `search_path`.

Tests: existing 97 pass against Postgres unmodified. Any that break
indicate dialect-divergence the audit didn't catch — fix in this PR.

Acceptance: `pytest -q` against Postgres exits 0.

#### A1.3  Drop `_is_sqlite()` branches in existing migrations — **S**

Files: `backend/alembic/versions/5928b093bf42_*.py` (the rename migration
that has the dialect branch). Drop the SQLite branch; keep only the
Postgres path.

Tests: A1.2 covers this.

Acceptance: `git grep "_is_sqlite" backend/` returns 0 hits.

#### A1.4  Promote every `DateTime` column to `TIMESTAMPTZ` — **L**

Files: every model file (`models/*.py`). Replace
`Mapped[datetime] = mapped_column(DateTime, …)` with
`Mapped[datetime] = mapped_column(DateTime(timezone=True), …)`.

Migration: one Alembic revision that `ALTER COLUMN … TYPE TIMESTAMPTZ
USING (col AT TIME ZONE 'UTC')` for every datetime column on every table.

Tests: drop every `replace(tzinfo=UTC)` in `routers/signups.py:48`,
`routers/feedback.py:60-61`, anywhere else they appear. Tests reading
timestamps now compare aware-vs-aware throughout.

Acceptance:
* `git grep "replace(tzinfo=UTC)" backend/` returns 0 hits.
* `git grep "datetime.utcnow" backend/` returns 0 hits (already true).

#### A1.5  Native enums on Postgres — **S**

Files: `models/email_dispatch.py`. Set `native_enum=True` on
`EmailChannel` and `EmailStatus` columns.

Migration: Alembic creates the enum types; dispatch table column types
flip to the named enum.

Tests: A1.2 covers this; add an explicit test that asserts the column
type is `email_channel` enum on Postgres.

#### A1.6  Drop SQLite-only partial-index syntax — **S**

Files: `models/events.py:50–58` — drop `sqlite_where`, keep
`postgresql_where`.

Migration: not needed (existing index already created on prod Postgres).

#### A1.7  CI matrix simplification — **S**

Files: `.github/workflows/ci.yml`.

Drop the SQLite job; the Postgres one is the only matrix entry.

#### A1.8  Update docs — **S**

Files: `README.md`, `docs/deploy.md`, `docs/architecture.md`. Replace every
"SQLite for dev, Postgres for prod" with "Postgres everywhere".

Acceptance for A1 as a whole: `git grep -i sqlite backend/ tests/` returns
only references inside the dropped-functionality discussion.

---

### A2 — Pydantic Settings

One `backend/config.py` with a `Settings(BaseSettings)`. Every
`os.environ[…]` becomes `settings.X`. Misconfig fails at boot, not on first
use. Blocks A4 and A7.

Estimate: 1.5 days.

#### A2.1  Add `backend/config.py` — **M**

Files: `backend/config.py` (new), `pyproject.toml` (`pydantic-settings`
dep).

Schema:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    # required, no default — fail at boot if missing
    jwt_secret: SecretStr
    email_encryption_key: SecretBytes  # validator: 32 bytes
    database_url: str  # validator: starts with postgresql
    cors_origins: list[HttpUrl]
    public_base_url: HttpUrl
    message_id_domain: str  # validator: looks like a domain

    # required only conditionally
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str | None = None
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: EmailStr = "noreply@opkomst.nu"
    smtp_port: int = 587
    scaleway_webhook_secret: SecretStr | None = None

    # optional
    sentry_dsn: str | None = None
    sentry_environment: Literal["development", "staging", "production"] = "production"
    sentry_traces_sample_rate: float = 0.0
    bootstrap_admin_email: EmailStr | None = None
    local_mode: bool = False
    email_batch_size: int = 200
    email_retry_sleep_seconds: float = 1.0
    rate_limit_storage_uri: str = "memory://"
    web_concurrency: int = 4
    opkomst_allow_unsigned_webhooks: bool = False

    @model_validator(mode="after")
    def smtp_required_when_smtp_backend(self):
        if self.email_backend == "smtp" and not self.smtp_host:
            raise ValueError("EMAIL_BACKEND=smtp requires SMTP_HOST")
        return self


settings = Settings()  # raises on import if env is bad
```

Acceptance: `python -c "from backend.config import settings; print(settings.public_base_url)"` works after sourcing `.env`; raises clearly on missing required fields.

#### A2.2  Migrate every `os.environ` read — **L**

Files (every one of these reads env directly today; migrate to `settings`):

* `backend/auth.py:14` — `JWT_SECRET`
* `backend/database.py:6` — `DATABASE_URL`
* `backend/main.py:73` — `CORS_ORIGINS`
* `backend/services/encryption.py:14–17` — `EMAIL_ENCRYPTION_KEY` (drop manual length validation, Pydantic does it)
* `backend/services/email/identifiers.py:15` — `MESSAGE_ID_DOMAIN`
* `backend/services/email/urls.py:11` — `PUBLIC_BASE_URL`
* `backend/services/email/config.py` — entire file becomes a thin re-export from settings
* `backend/services/email/backends.py` — `EMAIL_BACKEND`
* `backend/services/email/smtp.py:13–17` — `SMTP_*`
* `backend/services/email/sender.py` — `EMAIL_RETRY_SLEEP_SECONDS` (via the deleted config)
* `backend/services/rate_limit.py` — `RATE_LIMIT_STORAGE_URI`
* `backend/routers/webhooks.py:44–47` — `OPKOMST_ALLOW_UNSIGNED_WEBHOOKS`, `SCALEWAY_WEBHOOK_SECRET`
* `backend/routers/auth.py` — `BOOTSTRAP_ADMIN_EMAIL`
* `backend/seed.py` — `LOCAL_MODE`
* `backend/main.py` — `SENTRY_*`

After: `git grep "os.environ" backend/` returns 0 hits in the production code path (`config.py` is the only reader).

#### A2.3  Boot-time fail-fast — **S**

Files: `backend/main.py` and (after A4) the cron entrypoint(s) import
`from .config import settings` at the top so a misconfig fails before any
HTTP traffic.

Tests: a unit test that sets bad env vars (`MESSAGE_ID_DOMAIN=""`) and
confirms `Settings()` raises `ValidationError` with a clear message.

Acceptance: deploying with a missing required env var produces a single,
clear error message at startup, not a confusing 500 hours later.

---

### A3 — OpenAPI-driven frontend types

Backend Pydantic schemas become the single source of truth for the
frontend's TypeScript interfaces. Independent of A1/A2; can run in parallel.

Estimate: 1 day.

#### A3.1  Generate `openapi.json` from FastAPI — **S**

Files: `Makefile` (`make openapi` target),
`scripts/generate_openapi.py` (new).

Already a pre-commit hook regenerates `openapi.json` (per the audit); make
the contract explicit in `Makefile`.

#### A3.2  Add `openapi-typescript` + `openapi-fetch` — **S**

Files: `frontend/package.json`, `frontend/src/api/schema.ts` (generated,
committed), `frontend/src/api/client.ts` (re-exports a typed fetcher).

Generation: `npm run generate-types` runs `openapi-typescript ../openapi.json -o src/api/schema.ts`.

Pre-commit hook: regen + fail if `schema.ts` is dirty.

#### A3.3  Migrate one store (events) to use generated types — **M**

Files: `frontend/src/stores/events.ts`. Replace the hand-written
`interface EventOut` with `import type { components } from "@/api/schema"`
and use `components["schemas"]["EventOut"]`. Switch to `openapi-fetch`'s
`useApi().GET("/api/v1/events")` (or keep the existing fetcher with the
generated type — whichever's smaller).

Tests: existing tests pass; `npm run vue-tsc` clean.

#### A3.4  Migrate the remaining stores — **M**

Files: `stores/admin.ts`, `stores/chapters.ts`, `stores/feedback.ts`,
`stores/auth.ts`. Same pattern.

Acceptance: `git grep "^interface .*Out\|^export interface" frontend/src/stores/` returns 0 hits.

#### A3.5  Pre-commit hook for schema sync — **S**

Files: `.pre-commit-config.yaml`. Hook: regenerate `schema.ts`, fail if
working-tree differs from `HEAD`.

---

### A4 — External cron, drop APScheduler

Replace the `worker.py` long-running process with three cron-invoked
entrypoints. Depends on A2.

Estimate: 1 day.

#### A4.1  Add `backend/cli.py` — **M**

Files: `backend/cli.py` (new). Three entry-points, each does one sweep and
exits:

```python
# python -m backend.cli dispatch <channel>
# python -m backend.cli reap-partial
# python -m backend.cli reap-expired
# python -m backend.cli reap-post-event
```

Each one:
* loads `settings`,
* runs migrations idempotently (no-op if at head),
* runs the sweep,
* logs result counts to stdout (Coolify scrapes),
* exits 0 on success, ≠0 on uncaught exception (Coolify alerts).

Tests: each CLI invocation has a unit test that mocks the dispatcher /
reaper functions and asserts the right one fires.

#### A4.2  Configure Coolify cron — **S**

Files: `docs/deploy.md` updated with the cron stanzas. Coolify supports
"scheduled task" containers natively.

Cron schedule:

```
0 *  * * *   python -m backend.cli dispatch reminder
0 *  * * *   python -m backend.cli dispatch feedback
30 *  * * *   python -m backend.cli reap-partial
0 3  * * *   python -m backend.cli reap-expired
30 3 * * *   python -m backend.cli reap-post-event
```

(Slightly offset minutes so they don't all hit the DB at the same instant.)

#### A4.3  Delete `worker.py` and APScheduler — **S**

Files: delete `backend/worker.py`. `pyproject.toml` — drop `apscheduler`
dep.

Tests: any test that imports `backend.worker` is updated to import the
relevant CLI entrypoint instead.

#### A4.4  Boot-time reaper sweep stays — **S**

Move the boot-time `_safe_reap` block from `worker.py:62-69` into
`backend/main.py` startup. The API container does one defensive sweep on
boot; cron handles steady state.

#### A4.5  Drop `worker` service from `docker-compose.yml` — **S**

Files: `docker-compose.yml`, `Dockerfile` comments.

Acceptance: `git grep -i "apscheduler\|backgroundscheduler" backend/` returns 0 hits.

---

### A5 — Generic CRUD route helper

Independent of everything except 0.1. Can run anytime in week 1–2.

Estimate: 0.5 day.

#### A5.1  Add `backend/services/access.py` — **S**

Files: `backend/services/access.py` (new).

```python
def get_event_for_user(
    db: Session, entity_id: str, user: User,
    *, allow_archived: bool = False, public: bool = False,
) -> Event:
    """Single source of truth for event lookup with scoping."""
    q = scd2_svc.current(db.query(Event)).filter(Event.entity_id == entity_id)
    if not public and user.chapter_id is not None:
        q = q.filter(Event.chapter_id == user.chapter_id)
    elif not public and user.chapter_id is None:
        # User has no chapter — they can't see any event.
        raise HTTPException(404, "Event not found")
    event = q.first()
    if not event:
        raise HTTPException(404, "Event not found")
    if event.archived_at is not None and not allow_archived:
        raise HTTPException(410, "Event has been archived")
    return event
```

Plus equivalents for users / chapters.

#### A5.2  Migrate `routers/events.py` — **M**

Replace the `_get_event_scoped` helper + magic-string `"__no_match__"`
(line 62-64) + every inline check.

Lines touched: ~12 call sites in `events.py`.

#### A5.3  Migrate `routers/feedback.py` — **S**

Same pattern. Drops the duplicate scope-check at lines 167–177 and 300–310.

#### A5.4  Migrate `routers/admin.py` + `chapters.py` — **S**

Same pattern with `get_user_for_admin` / `get_chapter_for_admin`.

Acceptance: `git grep '"__no_match__"' backend/` returns 0 hits.

---

### A6 — Vue Query, retire hand-rolled Pinia stores

Depends on A3 (typed client makes the migration mechanical).

Estimate: 2 days.

#### A6.1  Wire `@tanstack/vue-query` — **S**

Files: `frontend/package.json`, `frontend/src/main.ts` (install
`VueQueryPlugin` + `QueryClient` configured with sensible
defaults — 30 s stale time, retry 1).

#### A6.2  Convert `stores/events.ts` to query hooks — **M**

Files: `frontend/src/composables/useEvents.ts` (new), delete
`frontend/src/stores/events.ts`.

```typescript
export function useEventList() {
  return useQuery({
    queryKey: ['events'],
    queryFn: () => api.GET('/api/v1/events').then(r => r.data!),
  });
}

export function useArchiveEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.POST(`/api/v1/events/${id}/archive`),
    onMutate: (id) => {
      // optimistic remove
      const prev = qc.getQueryData(['events']);
      qc.setQueryData(['events'], (old: EventOut[]) => old.filter(e => e.id !== id));
      return { prev };
    },
    onError: (err, _id, ctx) => qc.setQueryData(['events'], ctx?.prev), // rollback
    onSettled: () => qc.invalidateQueries({ queryKey: ['events'] }),
  });
}
```

Components: `DashboardPage.vue` and `EventDetailsPage.vue` updated to call
the composables.

Tests: existing tests pass; the rollback bug from § 8.1 of the hardening
plan is now structurally impossible.

#### A6.3  Convert `stores/chapters.ts` — **S**

Same pattern.

#### A6.4  Convert `stores/admin.ts` — **S**

Same pattern. **This is the one with the rollback bug.** After this PR
the bug is gone.

#### A6.5  Convert `stores/feedback.ts` — **S**

Same pattern.

#### A6.6  Keep `auth` as a thin Pinia store — **S**

Reason: auth state is *session* state (the JWT, the user object), not
server state. Vue Query is for server state. Keep
`frontend/src/stores/auth.ts` (~94 lines), but trim it: the `loaded` /
`user` refs stay; the `fetchMe()` action wraps a Vue Query call that
populates them.

#### A6.7  Update Vitest tests — **S**

Files: `frontend/src/__tests__/*.test.ts`. Every store-import line
changes; assertions on local state become assertions on hook output (use
`@testing-library/vue` + `@tanstack/vue-query`'s test helpers).

Acceptance: `npm run test` exits 0; `git grep "defineStore" frontend/src/`
returns one hit (auth) instead of five.

---

### A7 — Magic-link auth, drop bcrypt

Depends on A2 (Settings owns JWT_SECRET, magic-link TTL). Drops the
password column entirely; pre-launch is the right time.

Estimate: 2 days.

#### A7.1  Add `LoginToken` model + migration — **S**

Files: `backend/models/auth.py` (new — or extend an existing module),
`backend/alembic/versions/<rev>_add_login_token.py`.

```python
class LoginToken(UUIDMixin, TimestampMixin, Base):
    """One-shot magic-link token. Issued on /auth/login-link, redeemed
    on /auth/login. Single-use; deleted on redeem."""
    __tablename__ = "login_tokens"
    token: Mapped[str] = mapped_column(Text, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(Text, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

#### A7.2  Add `/auth/login-link` endpoint — **M**

Files: `backend/routers/auth.py`.

POST `/api/v1/auth/login-link` body: `{ email: str }`.
* Look up user; if not found, return 200 anyway (don't leak).
* Mint `LoginToken`; insert.
* Send email via the existing `send_email` (new template
  `templates/{nl,en}/login.html`).
* Return 200.

Rate-limit: 5/h per IP, 5/h per email (slowapi key function).

#### A7.3  Add `/auth/login` endpoint (token consumption) — **S**

Files: `backend/routers/auth.py`.

POST `/api/v1/auth/login` body: `{ token: str }`.
* Look up token; reject if expired or missing (410 Gone).
* Issue JWT (existing `create_token`).
* Delete token row.
* Return `AuthResponse`.

#### A7.4  Update frontend login page — **M**

Files: `frontend/src/pages/LoginPage.vue`. Becomes:

1. Email input → click "Send link".
2. Show "Check your inbox" confirmation.
3. The link in the email has `?token=XYZ` → frontend calls `/auth/login`
   with the token, stores the JWT, redirects to `/dashboard`.

Wire a new route `/auth/redeem?token=…` that auto-redeems and redirects.

#### A7.5  Drop password column + bcrypt + verify-email — **M**

Files:
* `backend/auth.py` — drop `_hash_password`, `_verify_password`, `bcrypt` import.
* `backend/models/users.py` — drop `password_hash` column.
* `backend/routers/auth.py` — drop the old `/auth/login` (password) and `/auth/verify-email` endpoints. (Registration via magic-link is implicitly verified; the verify-email flow becomes redundant.)
* `backend/alembic/versions/<rev>_drop_password.py` — drop the column.
* `backend/services/email/templates/{nl,en}/verify.html` — delete (no
  longer sent).
* `pyproject.toml` — drop `bcrypt` dep.
* `frontend/src/pages/RegisterPage.vue` — drop password field; "Register"
  button now sends a login link too (registration ≡ first login).
* `frontend/src/pages/VerifyEmailPage.vue` — delete.
* `frontend/src/router/index.ts` — drop the verify route.

Tests: full new auth-flow test (register → email → click link → JWT
issued).

Acceptance: `git grep -i bcrypt` returns 0 hits across the whole repo.

#### A7.6  Update `BOOTSTRAP_ADMIN_EMAIL` flow — **S**

The first registration that matches `settings.bootstrap_admin_email`
auto-promotes to admin. (Same as before, but the trigger is "first magic
link redemption matching the email" instead of "first password
registration matching the email".)

Tests: the existing test in `test_auth.py` is updated.

#### A7.7  Update README + docs — **S**

Files: `README.md`, `docs/deploy.md`. Replace any password mention with
magic-link.

---

## Phase B — Hardening on the smaller surface (weeks 4–7)

After Phase A, the surface to test is meaningfully smaller. Phase B is
broadly the existing § 1–12 of `hardening-plan.md`, retargeted.

### B1 — Privacy lockdown (week 4) — **L**

Per § 2 of `hardening-plan.md`. Specifically:

#### B1.1  Static enforcement of decrypt + encrypt + ciphertext-write call sites

Files: `tests/test_privacy.py` extended with:
* `test_encrypt_only_called_from_signups_router`
* `test_encrypted_email_writes_only_in_signups_dispatcher_reaper`

(AST-walk the backend tree; assert the import / call sites match a
hand-maintained allowlist.)

#### B1.2  Hypothesis property test for the wipe invariant

Files: `tests/test_privacy_invariant_property.py` (new).

Strategy generates random sequences of (signup, sweep, fail, retire,
reap, webhook, post-event-purge). After applying, asserts:
* `Signup.encrypted_email IS NULL` ⇔ no `pending` dispatch row.
* No row state regresses (sent → pending is forbidden).

#### B1.3  Token-expiry boundary tests

Files: `tests/test_feedback_token_expiry.py` (new).

Frozen-clock tests at `expires_at - 1s`, `expires_at`, `expires_at + 1s`.
Crossing DST.

#### B1.4  Post-event purge probe

Files: `tests/test_post_event_purge.py` extended.

Test: deliberately bypass the per-channel wipe (mock it to no-op),
advance clock 7 days, confirm the purge wipes the leftover ciphertext.
Proves the backstop works for *future* bugs.

#### B1.5  scd2-safety pre-commit check

Files: `.pre-commit-config.yaml`, `scripts/check_scd2.py` (new).

Block bare `db.query(SCD2Model)` without `valid_until IS NULL` filter or
a `# scd2-history-ok: <reason>` comment.

### B2 — State-machine + concurrency tests (week 4) — **M**

#### B2.1  State-transition table-test

Files: `tests/test_email_state_machine.py` (new).

20 (state, trigger) pairs in a parametrise table. Each asserts the
expected resulting state and that the wipe invariant holds.

#### B2.2  Two-worker race for FEEDBACK channel

Files: `tests/test_parallel_workers.py` extended. Currently REMINDER only.

#### B2.3  Webhook + worker race

Files: `tests/test_webhook_worker_race.py` (new).

Webhook arrives while worker has minted message_id but hasn't committed
status. Property: end state consistent regardless of which side wins.

#### B2.4  Reaper + worker race

Files: same family. Reaper running concurrently with sweep.

#### B2.5  Migration idempotency in CI

Files: `.github/workflows/ci.yml` — adds a step that runs `alembic upgrade
head` then runs it again on the upgraded DB; must succeed.

### B3 — Time correctness (week 4) — **S**

After A1 there are no naive datetimes left, so this is mostly extending
the existing property test.

#### B3.1  Property test extended to feedback delay, token TTL, post-event purge

Files: `tests/test_timezone_invariants.py` extended with three new
strategies.

#### B3.2  DST boundary explicit cases

Files: same. Hand-picked examples at NL DST transitions.

#### B3.3  Frontend Intl format snapshot test

Files: `frontend/src/__tests__/format.test.ts` (new). Locks the formatted
date string per locale.

### B4 — Email + webhook hardening (week 5) — **L**

#### B4.1  aiosmtpd integration test for SMTP backend

Files: `tests/test_smtp_backend_integration.py` (new),
`pyproject.toml` (`aiosmtpd` dev dep).

Spin up a local SMTP server in the test; assert the wire shape (From,
Message-ID, subject, body) of every send. **Closes the 0 % coverage on
`services/email/smtp.py`.**

#### B4.2  Per-attempt SMTP timeout

Files: `backend/services/email/sender.py`. Add explicit `timeout=5` to
`send_email_sync`.

Test: stub a slow SMTP that hangs past 5 s; assert the worker exits cleanly.

#### B4.3  Webhook fuzz tests

Files: `tests/test_webhook_fuzz.py` (new). Hypothesis-fuzzes JSON shape,
unicode, oversized body. Must always 204 / 401 / 503; never 500.

#### B4.4  Webhook rate-limit

Files: `backend/routers/webhooks.py` — `@limiter.limit("60/minute")`.

#### B4.5  Bounce-rate metric per event

Files: `backend/services/email_dispatcher.py`. After each finalise, emit a
`warning` log when the event's bounce-rate (over its current dispatches)
crosses 10 %.

#### B4.6  `/health` expansion

Files: `backend/main.py:88`. Add `schema_head`, `db_connectivity`,
`oldest_pending_dispatch_age_seconds`.

#### B4.7  Sentry-on-job-error for cron entry-points

Files: `backend/cli.py`. Wrap the sweep call in a try/except that
captures-and-reraises so Sentry sees the exception even though Coolify
will re-invoke. (After A4, APScheduler is gone, so this replaces the
audit's APScheduler `EVENT_JOB_ERROR` recommendation.)

### B5 — Public-surface security (week 5) — **M**

#### B5.1  Rate-limit gaps

Files: `routers/auth.py`, `routers/admin.py`, `routers/chapters.py`,
`routers/events.py`, `routers/webhooks.py`. Add the missing decorators
per the table in `hardening-plan.md` § 6.1.

Test: `tests/test_rate_limits_audit.py` (new). Iterates the FastAPI app
routes; asserts every public POST/PATCH/DELETE has a `@limiter.limit`
applied.

#### B5.2  SlowAPI storage decision committed

Files: `docs/deploy.md`. Decide: single-replica deploy ✓ (current), or
move `RATE_LIMIT_STORAGE_URI` to Redis. Document the choice.

#### B5.3  Auth-flow tests

Files: `tests/test_auth_flow.py` (new). Full register → magic-link →
admin-approve → first login → JWT-after-role-change → expiry → invalid-sig.

#### B5.4  Public-event archived 404

Files: `tests/test_public_archived.py` (new). Every public route on an
archived event returns 410 (or 404). Email-preview endpoints on archived
events: 404.

### B6 — Frontend coverage (week 6) — **L**

After A6 the stores are gone; tests target the composables and components.

#### B6.1  Vitest coverage for every composable

Files: `frontend/src/__tests__/use*.test.ts`. One test file per
composable. Target ≥ 80 %.

#### B6.2  `as` cast audit

Files: `frontend/src/**/*.{vue,ts}`. After A3, most casts are gone; audit
remaining ones and replace with type guards.

#### B6.3  Playwright happy-paths

Files: `e2e/*.spec.ts`. Add:
* anonymous signup flow (already in 0.5)
* organiser register + admin approve + first event
* email-preview button leads to a working page
* webhook bounce arrives → email-health reflects it on the dashboard

### B7 — Operational reliability (week 6) — **M**

#### B7.1  Backup + quarterly restore drill script

Files: `scripts/restore_drill.sh` (new), `docs/runbook.md` updated.

Quarterly: run the script in CI on a Saturday cron; alert if it fails.

#### B7.2  Worker shutdown timeout

After A4 there's no worker process. The cron entry-point already exits on
its own. The remaining concern is the API container handling SIGTERM
during a request — uvicorn handles it. No specific PR; document in the
runbook.

#### B7.3  Disk-space probe in /health

Files: `backend/main.py`. Add `disk_free_gb` to the health response. Alert
threshold: < 1 GB.

#### B7.4  Coolify env-var drift check

Files: `scripts/verify_env.py` (new), `docs/deploy.md`.

Loads `.env.example` keys, runs `Settings()` validation against the
deployed container's env. Run as a Coolify pre-deploy hook.

### B8 — Docs (week 7) — **M**

#### B8.1  Rewrite `docs/architecture.md`

Audit found three concrete drifts: Afdeling/Chapter rename,
feedback_*-columns vs SignupEmailDispatch, feedback_worker.py /
reminder_worker.py vs the channel-parametric dispatcher.

#### B8.2  Add `docs/runbook.md`

Five short scenarios with concrete commands, no prose:
* "the email queue is stuck"
* "a reminder fired twice"
* "a webhook keeps failing"
* "encryption key rotation"
* "restore from backup"

#### B8.3  Add `CLAUDE.md` for opkomst

Smaller than horeca's. Project identity, pre-launch rule, no SCD2 hard
delete, the four reapers, the privacy invariant, env-var contract (now
backed by Pydantic Settings).

#### B8.4  Update README

Verify run command, PUBLIC_BASE_URL guidance, magic-link flow.

#### B8.5  Phase-status docs

For each completed phase, a 1-page `docs/phase-A1-status.md` etc. with
the actual LoC delta and coverage delta vs. the targets in this plan.

---

## Coverage targets per phase

| phase | backend cov | frontend cov | E2E paths |
|---|---|---|---|
| start | 67 % | 0 % | 0 |
| 0 done | 67 % | smoke per page | 1 |
| A1 done | 70 % | smoke | 1 |
| A2 done | 72 % | smoke | 1 |
| A3 done | 72 % | smoke | 1 |
| A4 done | 70 % (worker.py gone, denominator shifts) | smoke | 1 |
| A5 done | 75 % | smoke | 1 |
| A6 done | 75 % | 60 % | 1 |
| A7 done | 80 % | 60 % | 2 |
| B1 done | 85 % | 60 % | 2 |
| B2 done | 88 % | 60 % | 2 |
| B3 done | 88 % | 65 % | 2 |
| B4 done | 92 % | 65 % | 2 |
| B5 done | 95 % | 65 % | 3 |
| B6 done | 95 % | 80 % | 4 |
| B7 done | 95 % | 80 % | 4 |
| B8 done | 95 % | 80 % | 4 |

The coverage gate in CI is bumped at the end of every PR that crosses a
threshold — never lowered.

---

## Per-PR effort summary

| PR | effort | depends on | week |
|---|---|---|---|
| 0.1 | M | — | 1 |
| 0.2–0.5 | S/S/M/M | 0.1 | 1 |
| A1.1 | S | 0.1 | 1 |
| A1.2 | M | A1.1 | 1 |
| A1.3–A1.8 | S each | A1.2 | 1–2 |
| A2.1 | M | A1.x (any) | 2 |
| A2.2 | L | A2.1 | 2 |
| A2.3 | S | A2.2 | 2 |
| A3.1–A3.5 | S/S/M/M/S | 0.1 | 1–2 |
| A4.1 | M | A2 | 2 |
| A4.2–A4.5 | S each | A4.1 | 2–3 |
| A5.1–A5.4 | S/M/S/S | 0.1 | 1–2 |
| A6.1–A6.7 | S each except A6.2 (M) | A3 | 2–3 |
| A7.1–A7.7 | varies | A2 | 3 |
| B1–B8 | varies | Phase A complete | 4–7 |

Total Phase A: ~14 days of focused work for one contributor.
Total Phase B: ~20 days of focused work for one contributor.

Two contributors in parallel: A1+A2+A4 sequential on one side,
A3+A5+A6+A7 on the other. Phase A in 1.5 weeks instead of 3.

---

## Acceptance criteria for plan completion

* `git grep -i "sqlite\|bcrypt\|apscheduler" backend/ tests/` returns 0
  hits in production code paths.
* `git grep "os.environ" backend/` returns 1 hit (`backend/config.py`).
* `git grep "interface .*Out\|interface .*In" frontend/src/stores/` returns
  0 hits.
* `git grep "defineStore" frontend/src/` returns 1 hit (auth).
* `git grep '"__no_match__"\|replace(tzinfo=UTC)' backend/` returns 0 hits.
* `pytest --cov=backend --cov-fail-under=95` passes.
* `npm run test -- --coverage` reports ≥ 80 % across `frontend/src/`.
* `npx playwright test` covers ≥ 4 happy paths.
* `docs/architecture.md` matches the code.
* CI is green on every PR.
* `Settings()` raises a clean error for every misconfig scenario.

When every line above is true, the codebase is in a state where a single
maintainer can leave it for six months and pick up cleanly: tests guard
the contracts, types prevent drift, and the structural shape eliminates
the bug classes that used to live in the cracks between modules.
