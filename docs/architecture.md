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
| `Afdeling` | Local chapter. Optional anchor city (display name + lat/lon) drives proximity bias on event-creation address autocomplete. |
| `Event` | Slug is partial-unique on the current version. `created_by` and `changed_by` reference `User.entity_id` (no FK — entity_id isn't unique across all rows). `archived_at` toggles for archive/restore. `locale` drives the public sign-up page language and the feedback email language. |

### Append-only / row-id-stable

| Model | Notes |
|---|---|
| `Signup` | `event_id` references `Event.entity_id`. Holds AES-GCM-encrypted email blob (nulled after the worker processes the signup). `feedback_email_status`, `feedback_message_id`, `feedback_sent_at` track delivery. |
| `FeedbackQuestion` | The five fixed questions, keyed for i18n. |
| `FeedbackToken` | One-time URL-safe token. `signup_id` + `event_id` (the latter as `entity_id`). Deleted on response submit or send-failure. |
| `FeedbackResponse` | `event_id` (entity_id), `question_id`, `submission_id` (random per submission). **No link to signup** by design — privacy invariant. |
| `AuditLog` | `actor_id` / `target_id` reference `User.entity_id`. Records approve / promote / demote / assign_afdeling / delete. |

## Privacy invariants (enforced at multiple layers)

1. **No PII in logs.** Routes log a route name + outcome only. The
   email send hop is the only place `to=` ever appears.
2. **Email decryption only by the feedback worker.** Static check:
   `tests/test_privacy.py::test_decrypt_only_called_from_feedback_worker`
   greps the backend tree for `encryption.decrypt` callers.
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
| `admin.py` | list users, approve, assign-afdeling, promote, demote, delete | admin |
| `afdelingen.py` | list, create, patch (name + city), archive, restore, usage | mixed |
| `events.py` | list, list-archived, create, by-slug, qr.png, update, archive, restore, send-feedback-emails-now, stats, signups | scoped to user's afdeling |
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

```
Public signup form (questionnaire_enabled=true)
  ↓ encryption.encrypt(email) → Signup.encrypted_email
  Signup.feedback_email_status = "pending"

Hourly worker tick (or organiser-triggered)
  ↓ for each pending signup whose event ended ≥24h ago
  Mint FeedbackToken (URL-safe random, 30-day TTL)
  Generate Message-ID (random hex @ MESSAGE_ID_DOMAIN)
  Decrypt email (only legitimate caller)
  Render Jinja template in event.locale
  Hand to backend (console / SMTP) with Message-ID header
    ↓ on success: status = "sent", message_id stored
    ↓ on failure-after-retry: status = "failed", token deleted, message_id discarded
  Wipe encrypted_email regardless

Scaleway TEM webhook
  ↓ POST /api/v1/webhooks/scaleway-email
  HMAC-SHA256 verify against SCALEWAY_WEBHOOK_SECRET
  Lookup signup by feedback_message_id
  BOUNCE_EVENTS → status = "bounced"
  COMPLAINT_EVENTS → status = "complaint"
  Soft bounces / deliveries / opens: ignored

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
