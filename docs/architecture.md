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
  server issues a JWT signed against the user's stable SCD2
  ``entity_id`` so the token survives every later edit
  (rename, role change, approval, chapter reassignment).
- **Geocoding**: PDOK Locatieserver for address autocomplete.
- **Email**: Pluggable backend (`console` / `smtp`), Jinja2 templates
  per locale, AES-GCM at rest.
- **Scheduling**: external cron via Coolify's Scheduled Tasks.
  Each tick is a one-shot ``python -m backend.cli ...`` invocation
  of the same container image; non-zero exit becomes a Coolify
  alert. No long-running scheduler container.

## Data model

### SCD2 dimensions

Every dimension model below mixes in `SCD2Mixin` (`backend/mixins.py`)
and uses the helpers in `backend/services/scd2.py`. A logical
entity is a chain of rows sharing one `entity_id`; the current row
has `valid_until IS NULL`. Public DTOs always expose `entity_id` as
`id` — clients never see a per-version row id.

| Model | Notes |
|---|---|
| `User` | Email is partial-unique on the current version. JWTs sign `entity_id`, so tokens survive role / approval / chapter changes. Soft-delete = `scd2_close`; re-register with the same email restores the chain (unapproved). |
| `Chapter` | Local chapter. Optional anchor city (display name + lat/lon) drives proximity bias on event-creation address autocomplete. |
| `Event` | Slug is partial-unique on the current version. `created_by` and `changed_by` reference `User.entity_id` (no FK — entity_id isn't unique across all rows). `archived_at` toggles for archive/restore. `locale` drives the public sign-up page language and the feedback email language. |

### Append-only / row-id-stable

| Model | Notes |
|---|---|
| `Signup` | `event_id` references `Event.entity_id`. Holds AES-GCM-encrypted email blob (nulled after every dispatch row pointing at the signup is finalised). |
| `SignupEmailDispatch` | One row per (signup, channel). `status` cycles ``pending`` → ``sent`` / ``failed`` / ``bounced`` / ``complaint``. `message_id` is pre-minted before SMTP for the bounce-webhook lookup. Replaced the per-channel `feedback_email_status` / `reminder_email_status` triplets that used to live on `Signup`. |
| `LoginToken` | One-shot magic-link token. URL-safe random, 30-min TTL. Deleted on redeem; the daily ``reap-login-tokens`` cron purges expired rows. |
| `FeedbackQuestion` | The five fixed questions, keyed for i18n. |
| `FeedbackToken` | One-time URL-safe token. `signup_id` + `event_id` (the latter as `entity_id`). Deleted on response submit or send-failure. |
| `FeedbackResponse` | `event_id` (entity_id), `question_id`, `submission_id` (random per submission). **No link to signup** by design — privacy invariant. |
| `AuditLog` | `actor_id` / `target_id` reference `User.entity_id`. Records approve / promote / demote / assign_chapter / delete. |

## Privacy invariants (enforced at multiple layers)

1. **No PII in logs.** Routes log a route name + outcome only. The
   email send hop is the only place `to=` ever appears.
2. **Email decryption only by the email dispatcher.** Static
   check: `tests/test_privacy.py::test_decrypt_only_called_from_email_dispatcher`
   greps the backend tree for `encryption.decrypt` callers and
   pins the allowlist (the channel-parametric dispatcher is the
   one legitimate caller).
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
| `auth.py` | login-link (request), login (redeem token), register (mints link), /me | public POST + bearer; rate-limited |
| `admin.py` | list users, approve, assign-chapter, promote, demote, delete | admin |
| `chapters.py` | list, create, patch (name + city), archive, restore, usage | mixed |
| `events.py` | list, list-archived, create, by-slug, qr.png, update, archive, restore, send-emails-now (per channel), stats, signups | scoped to user's chapter |
| `signups.py` | public POST | none (public); rate-limited |
| `feedback.py` | questions list, public form GET, public submit, organiser summary, organiser submissions list (CSV source) | mixed; rate-limited on public submit |
| `webhooks.py` | scaleway-email | HMAC if `SCALEWAY_WEBHOOK_SECRET` is set |

## Frontend page graph

| Page | Path | Auth |
|---|---|---|
| LoginPage | `/login` | public; redirects authed visitors to `/dashboard` |
| RegisterPage | `/register` | public |
| RedeemPage | `/auth/redeem?token=` | public (one-shot magic-link landing) |
| DashboardPage | `/dashboard` | required (events list with search + skeleton loading) |
| AdminPage | `/admin` | admin (chapters + users with city picker, search, skeleton loading) |
| EventFormPage | `/events/new`, `/events/:id/edit` | approved (locale picker, draft persisted to localStorage) |
| EventDetailsPage | `/events/:id/details` | approved (overview + signups + per-submission CSV export) |
| ArchivedEventsPage | `/events/archived` | approved |
| QuestionnairePreviewPage | `/questionnaire` | approved |
| PublicEventPage | `/e/:slug` | public (locale follows event) |
| FeedbackPage | `/e/:slug/feedback?t=` | public (locale follows event) |

## Email pipeline

The dispatcher is channel-parametric: one
``email_dispatcher.run_once(spec)`` function, one
``ChannelSpec`` per channel
(``services/email_channels.py::REMINDER`` and ``FEEDBACK``). A
new channel is a config change — a new ``ChannelSpec`` plus a
template — never a parallel code path.

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

Scaleway TEM webhook
  ↓ POST /api/v1/webhooks/scaleway-email
  HMAC-SHA256 verify against SCALEWAY_WEBHOOK_SECRET (fail
    closed: 503 if secret unset)
  Single indexed lookup on dispatch.message_id (covers both
    channels with one query).
  Conditional UPDATE filtered on status='sent' so a row that
    already moved to a final state isn't downgraded.
  BOUNCE_EVENTS → status='bounced'
  COMPLAINT_EVENTS → status='complaint'
  Soft bounces / deliveries / opens: ignored.
  After every flip: per-event bounce-rate check; ≥10 % over
    ≥5 finalised dispatches emits a ``high_bounce_rate``
    structured warning.

Daily reapers (cron)
  reap-partial — flip orphaned PENDING+message_id rows to
    FAILED (mid-send crash recovery), wipe orphaned ciphertext.
  reap-expired — DELETE pending REMINDER rows whose event
    already started.
  reap-post-event-emails — wipe ciphertext + FAIL pending
    dispatches for events that ended ≥7 days ago. Backstop;
    under normal operation a no-op.
  reap-login-tokens — DELETE expired magic-link rows.

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

- `POST /auth/register` — 5/hour
- `POST /auth/login-link` — 5/hour
- `POST /auth/login` — 20/minute (token redemption)
- `POST /events/by-slug/{slug}/signups` — 30/hour
- `POST /feedback/{token}/submit` — 20/hour
- Default fallback on every other endpoint — 120/minute

## Tests

- `tests/` (pytest) — auth flow, SCD2 chains, privacy invariants,
  rate limiting. Per-test tempfile DB; no `:memory:` because of
  SQLAlchemy connection-pool isolation.
- `frontend/src/__tests__/` (vitest) — pure-function lib tests
  (`format`, `validate`, `event-urls`, `map-link`).
- `frontend/e2e/` (Playwright) — critical path: organiser logs in,
  creates event, public visitor signs up.

## Pre-commit

`lefthook.yml` wires `scripts/check_scd2_safety.sh` (flags any bare
`db.query(SCD2Model)` without a `valid_until` filter or `current(...)`
helper), plus `ruff` + `pyright`.

## Deployment

`Dockerfile` is multi-stage (frontend bundle → Python runtime). The
runtime serves the SPA from `frontend/dist/` and the API at
`/api/v1/`. See `docs/deploy.md` for Coolify steps and operations
notes.
