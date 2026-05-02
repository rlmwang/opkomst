# Architecture

A snapshot of how opkomst is wired today. Update this file alongside
the code — it's the canonical reference for "what's actually here",
not what we're aspiring to.

## Stack

- **Backend**: FastAPI on Python 3.13, SQLAlchemy 2.0, Alembic.
  Postgres everywhere — local dev runs the docker-compose ``postgres``
  service (``make db-up``), prod uses Coolify's managed Postgres.
- **Frontend**: Vue 3 Composition API + TypeScript + Vite + Pinia +
  PrimeVue 4. Routes lazy-loaded; vendor chunks split (`vue`,
  `i18n`, `primevue`).
- **Auth**: passwordless magic-link sign-in. Emails carry a
  one-shot ``LoginToken`` (URL-safe, 30-min TTL); on redemption the
  server issues a JWT signed against ``user.id`` (a stable
  uuid7 PK).
- **Geocoding**: PDOK Locatieserver for address autocomplete.
- **Email**: Pluggable backend (`console` / `smtp`), Jinja2 templates
  per locale, AES-GCM at rest.
- **Scheduling**: external cron via Coolify's Scheduled Tasks.
  Each tick is a one-shot ``python -m backend.cli ...`` invocation
  of the same container image; non-zero exit becomes a Coolify
  alert. No long-running scheduler container.

## Data model

Flat tables with FK relationships. ``User`` and ``Chapter`` carry
a ``deleted_at`` column for soft-delete; ``Event`` carries
``archived_at``. Edits overwrite in place; the audit log carries
admin-driven change history.

### Soft-delete dimensions

| Model | Notes |
|---|---|
| `User` | Email is partial-unique across live rows (``deleted_at IS NULL``). Re-registering a soft-deleted email un-deletes the row. JWT `sub` is `user.id` — a soft-delete invalidates the JWT (the lookup filters on `deleted_at IS NULL`). |
| `Chapter` | Local chapter. Soft-delete via `deleted_at`; restore clears the column. Name unique across live chapters. Optional anchor city drives proximity bias on event-creation address autocomplete. |
| `UserChapter` | Many-to-many user↔chapter membership. Composite PK ``(user_id, chapter_id)``; CASCADE on user / chapter hard-delete; preserved on chapter soft-delete (a restore brings members back). Read paths filter on ``Chapter.deleted_at IS NULL`` so soft-deleted memberships drop out of /me, the access scope, and admin usage counts. |

### Archive-only

| Model | Notes |
|---|---|
| `Event` | `archived_at` toggles for archive/restore. `created_by` is a real FK to `User.id` (`ON DELETE SET NULL`); `chapter_id` likewise FKs `Chapter.id`. Slug is unique across the table — archive doesn't free the slug since it may be in bookmarks. `locale` drives the public sign-up page language and the feedback email language. |

### Append-only / row-id-stable

| Model | Notes |
|---|---|
| `Signup` | `event_id` FK to `Event.id` (`ON DELETE CASCADE`). Holds AES-GCM-encrypted email blob (nulled after every dispatch row pointing at the signup is finalised). |
| `EmailDispatch` | One row per (event, channel). `status` cycles ``pending`` → ``sent`` / ``failed`` (terminal). `message_id` is pre-minted before SMTP so a process crash mid-send is recoverable by the partial-sends reaper, and ends up on the outbound `Message-ID:` header so log lines correlate with provider-side records. |
| `LoginToken` | One-shot sign-in magic-link token. URL-safe random, 30-min TTL. Deleted on redeem; the daily ``reap-auth-tokens`` cron purges expired rows. |
| `RegistrationToken` | One-shot "finish creating your account" token, minted when ``/auth/login-link`` receives an unknown email. Keyed on the email (no ``User`` row yet); URL-safe random, 30-min TTL. Single outstanding token per email — a fresh ``/auth/login-link`` for the same unknown email deletes the prior row. Deleted on every terminal outcome of ``/auth/complete-registration`` (success, expired, race) and reaped daily by ``reap-auth-tokens``. |
| `FeedbackQuestion` | The five fixed questions, keyed for i18n. |
| `FeedbackToken` | One-time URL-safe token. `signup_id` + `event_id` FKs. Deleted on response submit or send-failure. |
| `FeedbackResponse` | `event_id`, `question_id`, `submission_id` (random per submission). **No link to signup** by design — privacy invariant. |
| `AuditLog` | `actor_id` / `target_id` reference `User.id` (no FK so a soft-deleted user's history survives). Records approve / promote / demote / assign_chapter / delete. |

## Privacy invariants (enforced at multiple layers)

1. **No PII in logs.** Routes log a route name + outcome only. The
   email send hop is the only place `to=` ever appears.
2. **Email decryption only by the lifecycle worker.** Static
   check: `tests/test_privacy.py::test_decrypt_only_called_from_mail_lifecycle`
   greps the backend tree for `encryption.decrypt` callers and
   pins the allowlist (`mail_lifecycle.py` is the one
   legitimate caller).
3. **Encrypted email is hard-deleted after the worker runs**
   (success or failure-after-retry).
4. **Feedback responses are not linkable to signups.** No
   `signup_id` column on `FeedbackResponse`.
5. **Open-source disclosure on every public sign-up form.**
6. **Per-event `questionnaire_enabled` gate** — when off, the email
   field disappears from the public form and the worker never
   touches the event.

## Routers

All under `/api/v1/`.

| Router | Endpoints | Auth |
|---|---|---|
| `auth.py` | login-link (request — branches on whether email is registered), login (redeem login token), complete-registration (redeem registration token + supply name), /me | public POST + bearer; rate-limited |
| `admin.py` | list users, approve (multi-chapter), set-chapters (replace full membership set), promote, demote, rename, delete | admin |
| `chapters.py` | list, create, patch (name + city), archive, restore, usage | mixed |
| `events.py` | list, list-archived, create, by-slug, qr.svg, update, archive, restore, send-emails-now (per channel), stats, signups | scoped to user's chapter set; ``?chapter_id=`` narrows the list to one chapter (validated against the user's set) |
| `signups.py` | public POST | none (public); rate-limited |
| `feedback.py` | questions list, public form GET, public submit, organiser summary, organiser submissions list (CSV source) | mixed; rate-limited on public submit |

## Frontend page graph

| Page | Path | Auth |
|---|---|---|
| LoginPage | `/login` | public; redirects authed visitors to `/events` |
| RegisterCompletePage | `/register/complete?token=` | public (one-shot registration-link landing — asks for name, returns a JWT) |
| RedeemPage | `/auth/redeem?token=` | public (one-shot magic-link landing) |
| DashboardPage | `/events` | required (events list with search + skeleton loading) |
| AdminPage | `/admin` | admin (chapters + users with city picker, search, skeleton loading) |
| EventFormPage | `/events/new`, `/events/:id/edit` | approved (locale picker, draft persisted to localStorage) |
| EventDetailsPage | `/events/:id/details` | approved (overview + signups + per-submission CSV export) |
| ArchivedEventsPage | `/events/archived` | approved |
| QuestionnairePreviewPage | `/questionnaire` | approved |
| PublicEventPage | `/e/:slug` | public (locale follows event) |
| FeedbackPage | `/e/:slug/feedback?t=` | public (locale follows event) |

## Email pipeline

The lifecycle worker handles every channel: one
``mail_lifecycle.run_once(channel)`` function, with the per-
channel deltas (window predicate, template, context builder,
feedback's token mint) as explicit ``if channel == ...``
branches inside ``mail_lifecycle.py``. A new channel is a new
``EmailChannel`` enum value, a window predicate, a context
builder, a template, and a branch — never a parallel code path.

```
Public signup form
  ↓ encryption.encrypt(email) → Signup.encrypted_email
  For each channel applicable to this event (toggle on +
  email present + window viable), insert a SignupEmailDispatch
  row with status='pending'.

Hourly cron tick (or organiser "send now" button)
  python -m backend.cli dispatch reminder
  python -m backend.cli dispatch feedback
  ↓ for each PENDING dispatch whose event satisfies the
    channel's window predicate
  Conditional UPDATE pre-mints message_id (atomic claim:
    filtered on status='pending' AND message_id IS NULL).
  Decrypt Signup.encrypted_email (only legitimate caller).
  Per-channel pre-send hook (e.g. feedback mints FeedbackToken).
  Render Jinja template in event.locale.
  send_with_retry — one retry on flap, then Sentry-captured
    failure.
    ↓ success: status='sent', message_id stored, sent_at = now
    ↓ failure: status='failed', message_id NULL, sent_at = now,
      per-channel on_failure hook runs (feedback deletes the
      FeedbackToken)
  Wipe Signup.encrypted_email iff no PENDING dispatch row
    pointing at this signup remains.

Daily reapers (cron)
  reap-partial — flip orphaned PENDING+message_id rows to
    FAILED (mid-send crash recovery), wipe orphaned ciphertext.
  reap-expired — finalise pending dispatches whose channel
    window has long passed: REMINDER for events whose
    starts_at is in the past, FEEDBACK for events that ended
    ≥7 days ago. Wipes ciphertext on the same UPDATE. Under
    normal operation a near-no-op; non-zero result signals a
    drift somewhere upstream.
  reap-auth-tokens — DELETE expired login + registration magic-link rows.

Public submission /api/v1/feedback/{token}/submit
  ↓ Validate token + required questions
  Generate submission_id (random)
  Insert FeedbackResponse rows (event_id only)
  Delete FeedbackToken (one-shot)
```

## Security headers

`SecurityHeadersMiddleware` (`backend/services/security_headers.py`)
sets on every response:

- Pinned CSP — allows OSM tile server, Photon, PDOK, and PrimeVue's
  runtime style injection (`'unsafe-inline'` for `style-src` only).
- HSTS (only on HTTPS requests).
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` denying every device API.

## Rate limiting

`slowapi`, in-process by default (set `RATE_LIMIT_STORAGE_URI` to a
Redis URL for multi-replica). Per-IP limits:

- `POST /auth/login-link` — 5/hour
- `POST /auth/login` — 20/minute (token redemption)
- `POST /auth/complete-registration` — 20/minute (token redemption)
- `POST /events/by-slug/{slug}/signups` — 30/hour
- `POST /feedback/{token}/submit` — 20/hour
- Default fallback on every other endpoint — 120/minute

## Tests

- `tests/` (pytest) — auth flow, soft-delete + restore round-
  trips, privacy invariants, rate limiting, email lifecycle
  state machine. Per-test fresh database via the conftest ``db``
  fixture.
- `frontend/src/__tests__/` (vitest) — composable smokes,
  optimistic-update rollbacks, format/i18n helpers.
- `frontend/e2e/` (Playwright) — critical path: organiser logs
  in, creates event, public visitor signs up.

## Pre-commit

`ruff` + `pyright` via `lefthook.yml`. CI also runs the rate-
limit audit (every mutating endpoint must carry a
`@limiter.limit` decorator), schema-drift gate (regenerated
`openapi.json` matches the committed copy), and migration-
idempotency (`alembic downgrade base ; upgrade head ; upgrade
head` succeeds).

## Deployment

`Dockerfile` is multi-stage (frontend bundle → Python runtime). The
runtime serves the SPA from `frontend/dist/` and the API at
`/api/v1/`. See `docs/deploy.md` for Coolify steps and operations
notes.
