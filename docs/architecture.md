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
| `Chapter` | Local chapter. Soft-delete via `deleted_at`; restore clears the column. Name unique across live chapters. Human-readable `slug` (unique across live chapters, never the 8-char event shape) drives the public agenda at `/e/{chapter}`. Optional anchor city drives proximity bias on event-creation address autocomplete. |
| `UserChapter` | Many-to-many user↔chapter membership. Composite PK ``(user_id, chapter_id)``; CASCADE on user / chapter hard-delete; preserved on chapter soft-delete (a restore brings members back). Read paths filter on ``Chapter.deleted_at IS NULL`` so soft-deleted memberships drop out of /me, the access scope, and admin usage counts. |

### Archive-only

| Model | Notes |
|---|---|
| `Event` | The **definition** — the shared content plus a recurrence rule (`first_starts_at`/`first_ends_at` anchor, `cadence_weeks`, `occurrence_count` span [null = open-ended, 1 = one-off], `horizon_days`). No single date: concrete dates are `Occurrence` rows. `archived_at` toggles for archive/restore. `created_by` is a real FK to `User.id` (`ON DELETE SET NULL`); `chapter_id` likewise FKs `Chapter.id`. The event's own slug is organiser-internal; the public slug lives on `Occurrence`. `listed` (default true) controls whether the event's occurrences show on its chapter's public agenda. `locale` drives the public sign-up page + feedback email language. |
| `Occurrence` | A materialised, dated instance of an `Event` (`event_id` FK, `ON DELETE CASCADE`). Carries only what is its own: `index` (0-based, for "sessie i van N"), its own public `slug` (`/e/{slug}`), and `starts_at`/`ends_at` (materialised = anchor shifted `index * cadence_weeks` whole weeks). All content is read through `event_id`. Materialised over time by the `event-tick` cron inside `horizon_days`; a one-off's single occurrence is created at event-creation. `UNIQUE(event_id, index)`. |
| `Registration` | One person's booking (the order header) against an event: `event_id` FK, `display_name` (optional pseudonym), `party_size`, and the single edit-link (`edit_token_hash` + `link_recovered_at` from `EditTokenMixin`). No email column — the address lives only on the per-occurrence `EmailDispatch` rows. |
| `Form` | Standalone questionnaire. Same `archived_at` shape as `Event`; same chapter scoping. No relation to `Event`. `slug` is unique across the table; public fill-out lives at `/f/:slug`. |

### Append-only / row-id-stable

| Model | Notes |
|---|---|
| `Signup` | A booking's **line item**: one `Registration` (`registration_id` FK, `ON DELETE CASCADE`) attending one `Occurrence` (`occurrence_id` FK, `ON DELETE CASCADE`), plus that line's `source_choice` + `help_choices`. `UNIQUE(registration_id, occurrence_id)`. No email — the address graph keys on the occurrence and never references a line item. Signing up for several sessions at once is one registration with several line items. |
| `EmailDispatch` | One row per (occurrence, channel, attendee). Holds the AES-GCM-encrypted address (nulled the instant the row finalises). `status` cycles ``pending`` → ``sent`` / ``failed`` (terminal). `message_id` is pre-minted before SMTP so a process crash mid-send is recoverable by the partial-sends reaper, and ends up on the outbound `Message-ID:` header so log lines correlate with provider-side records. |
| `LoginToken` | One-shot sign-in magic-link token. URL-safe random, 30-min TTL. Deleted on redeem; the daily ``reap-auth-tokens`` cron purges expired rows. |
| `RegistrationToken` | One-shot "finish creating your account" token, minted when ``/auth/login-link`` receives an unknown email. Keyed on the email (no ``User`` row yet); URL-safe random, 30-min TTL. Single outstanding token per email — a fresh ``/auth/login-link`` for the same unknown email deletes the prior row. Deleted on every terminal outcome of ``/auth/complete-registration`` (success, expired, race) and reaped daily by ``reap-auth-tokens``. |
| `FeedbackQuestion` | The five fixed questions, keyed for i18n. |
| `FeedbackToken` | One-time URL-safe token. `occurrence_id` FK only (feedback is per occurrence). No `signup_id` — the token never references the attendee it authorises. Deleted on response submit or send-failure. |
| `FeedbackResponse` | `occurrence_id`, `question_key`, `submission_id` (random per submission). **No link to signup** by design — privacy invariant. |
| `FormQuestion` | Per-form question rows. `form_id` FK (`ON DELETE CASCADE`). `kind` is one of `rating` / `text` / `short_text` / `single_choice` / `multi_choice`; the enum is enforced at the schema layer and the public submit handler. `options` is a JSON list for the two choice kinds; `low_label` / `high_label` are the optional scale captions for `rating`. Diff-applied by id on update — renaming or reordering doesn't reset the row's identity, so its responses stay attached. |
| `FormResponse` | One row per (submission, question). `submission_id` is a random per-submission token with **no link** to any user or session — same privacy invariant as `FeedbackResponse`. `form_id` cascades; `question_id` also cascades, so an organiser dropping a question deletes the responses to it. |
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
| `events.py` | list, list-archived, create (materialises occurrences), update (reconciles future occurrences), archive, restore, send-emails-now (per channel), stats, occurrence list, per-occurrence signups, image upload (4:3 hero, PUT to GitHub Contents API → ``raw.githubusercontent.com``; 503 when ``GITHUB_IMAGES_*`` unset), image delete | scoped to user's chapter set; ``?chapter_id=`` narrows the list to one chapter (validated against the user's set) |
| `events_public.py` | by-slug (occurrence), event.ics, qr.svg, feedback-preview, email-preview — all keyed by the public occurrence slug | none (public) |
| `signups.py` | public multi-occurrence booking POST (by occurrence slug), booking edit + per-occurrence withdraw (by token), organiser edit-link recover + line-item delete | none on public paths (rate-limited); organiser paths scoped |
| `feedback.py` | questions list, public form GET, public submit, organiser summary, organiser submissions list (CSV source) | mixed; rate-limited on public submit |
| `forms.py` | list, list-archived, create, get, update (diff-applies the question payload), archive, restore, delete-only-when-archived, summary, submissions (CSV source) | scoped to user's chapter set; same lifecycle shape as events.py |
| `forms_public.py` | public form fetch by slug, public submit | none (public); rate-limited on submit; archived forms 410 |

## Frontend page graph

| Page | Path | Auth |
|---|---|---|
| LoginPage | `/login` | public; redirects authed visitors to `/events` |
| RegisterCompletePage | `/register/complete?token=` | public (one-shot registration-link landing — asks for name, returns a JWT) |
| RedeemPage | `/auth/redeem?token=` | public (one-shot magic-link landing) |
| DashboardPage | `/events` | required (events list with search + skeleton loading) |
| AdminPage | `/admin` | admin (chapters + users with city picker, search, skeleton loading) |
| EventFormPage | `/events/new`, `/events/:id/edit` | approved (locale picker, draft persisted to localStorage) |
| EventDetailsPage | `/events/:id/details` | approved (overview + read-only occurrence list with per-occurrence signups + per-submission CSV export) |
| ArchivedEventsPage | `/events/archived` | approved |
| QuestionnairePreviewPage | `/questionnaire` | approved |
| PublicEventPage | `/e/:slug` | public (`:slug` is an **occurrence** slug; the sign-up form offers a checklist of the event's upcoming occurrences + an "all upcoming" shortcut. locale follows event; served by ``spa.py`` as a separate mini-app — payload + OG meta inlined into the HTML) |
| PublicChapterAgenda | `/e/:chapter` | public (separate mini-app; the `/e/` handler dispatches by slug shape: an 8-char occurrence slug serves the sign-up page, anything else is a chapter slug → the agenda grid of that chapter's upcoming + recent-past **occurrences**, each its own card) |
| FeedbackPage | `/e/:slug/feedback?t=` | public (locale follows event) |
| FormListPage | `/forms` | required (active forms list; reuses ``ListPageView``) |
| ArchivedFormsPage | `/forms/archived` | approved |
| FormEditPage | `/forms/new`, `/forms/:id/edit` | approved (name + chapter + locale + question editor; reuses ``FormPageShell``) |
| FormDetailsPage | `/forms/:id/details` | approved (overview + per-question response aggregates + CSV export; reuses ``DetailsPageShell``) |
| PublicFormPage | `/f/:slug` | public (separate mini-app; same inlined-payload + OG-meta shape as ``/e/:slug``) |

## Branding

Everything visual about an organisation is data on disk, not code:

```
brands/rsp/
  brand.json      app + org name, wordmark, org URL, mail From name,
                  the six literal palette values, and the image filenames
  tokens.css      the palette as custom properties (--brand-*), including
                  the PrimeVue primary + surface ramps
  logo.png  favicon.png  apple-touch-icon.png
```

The folder is served at `/brand/{tenant}/…` (`spa.py`, an hour's cache —
these filenames are stable, unlike the content-hashed Vite assets), and
never enters the bundle. Every HTML shell carries an
`<!-- OPKOMST_BRAND_INJECTION -->` marker that
`services/brand.py::head` fills with the boot colours, the stylesheet
link, the two icons and `window.__OPKOMST_BRAND__`; the Vite dev server
substitutes the identical markup, so dev and prod heads agree.

Consequences worth knowing:

- `theme.css` and the component styles name no colour — they read
  `var(--brand-*)`, which the tenant's `tokens.css` defines.
- `primevue-preset.ts` maps PrimeVue's design tokens onto those same
  variables, so one preset tints every widget for whichever brand the
  page is wearing.
- Email is the one place the palette appears as literal values
  (`{{ brand.palette.* }}` in `base.html`) — mail clients don't support
  `var()` — and the logo is absolute for the same reason.
- `scripts/check_brand_tokens.py` (pre-commit + CI) fails the build on a
  hex literal, an `rgb()`/`hsl()` that isn't a black/white scrim, or a
  brand image referenced by filename, anywhere outside `brands/`.

Which brand a page wears is decided per request: the organiser app by
the tenant in its URL, a public page by the tenant that owns the entity
behind the slug, and email by the tenant bound to the send. A page whose
slug resolves to nothing wears `brands/opkomst/` — the house brand,
which deliberately carries no images, so a dead link never shows
somebody's logo.

## Tenants

One organisation per tenant; `tenants.slug` is both the organiser app's
URL prefix (`opkomst.nu/rsp/events`) and the brand-folder name.

- **Every table carries `tenant_id`** (NOT NULL, indexed, RESTRICT to
  `tenants`) via `TenantMixin`. On child rows it is denormalized from
  the parent so every filter and uniqueness rule is a single-column
  predicate. `tests/test_tenancy.py` guards both halves: the column
  exists everywhere, and no child disagrees with its parent.
- **Writes never name it.** The column defaults to the tenant bound to
  the current context (`services/tenancy.py`); a write with nothing
  bound raises rather than guessing.
- **Who binds it.** `TenantBindingMiddleware` binds from the JWT's
  `tenant` / `tenant_slug` claims — middleware, not a dependency,
  because a sync dependency runs in a worker thread whose context the
  endpoint never sees. Public routes bind from the entity the slug
  resolved to (`services/public_access.py` and the by-slug getters).
  The CLI, the seeds and the two ticks bind per item with
  `tenancy.use(...)`.
- **Reads.** `access.get_scoped` adds `tenant_id == user.tenant_id` on
  top of the chapter scope; chapter queries start from a tenant-scoped
  base. `role=admin` means global *within one organisation*.
- **Uniqueness.** `users.email` and `chapters.name` are unique per
  tenant among live rows. `chapters.slug` stays globally unique — the
  agenda at `/e/{slug}` carries no tenant, so two organisations cannot
  both own `amsterdam`; the existing suffixer hands out `amsterdam-2`.
- **Creating one** is `python -m backend.cli tenant-create --slug rsp
  --name RSP`, and it refuses a slug with no brand folder. There is no
  UI and no platform-level role: nobody signs in to the platform, only
  to a tenant.
- **URLs.** Organiser: `/{tenant}/…`, with the router's history base
  read from the injected brand. Public: unchanged and tenant-free
  (`/e/`, `/f/`, `/d/`, `/c/`). The bare root 404s.

## Email pipeline

The lifecycle worker handles every channel: one
``mail_lifecycle.run_once(channel)`` function, with the per-
channel deltas (window predicate, template, context builder,
feedback's token mint) as explicit ``if channel == ...``
branches inside ``mail_lifecycle.py``. A new channel is a new
``EmailChannel`` enum value, a window predicate, a context
builder, a template, and a branch — never a parallel code path.

```
Public signup form (one booking over the picked occurrences)
  ↓ create one Registration + one Signup line item per occurrence
  For each occurrence × channel applicable (toggle on + email
  present + window viable), insert an EmailDispatch row keyed on
  the occurrence with status='pending' and encryption.encrypt(email).

Hourly cron tick (or organiser "send now" button)
  python -m backend.cli dispatch reminder
  python -m backend.cli dispatch feedback
  ↓ for each PENDING dispatch whose occurrence satisfies the
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
