# Design: respondent edit link (magic link to revisit a submission)

Status: proposed. Lets a public respondent go back and change what they
submitted, for all three entity types (event sign-up, form submission,
datepoll submission), via a per-submission magic link shown on the
confirmation page.

## Goal & UX

After submitting, the confirmation card shows a **magic edit link** with
a **copy button** (the same copy affordance used elsewhere), a one-line
explainer, and a warning that the link can't be recovered once the page
is closed.

```
┌───────────────────────────────────────────────┐
│  Bedankt!                                       │
│  Je reactie is binnen.                          │
│                                                 │
│  Wil je je antwoord later aanpassen?            │
│  https://opkomst.nu/d/ab12cd34?s=…   [Kopieer]  │
│  Bewaar deze link — we kunnen 'm niet opnieuw   │
│  sturen nadat je deze pagina sluit.             │
└───────────────────────────────────────────────┘
```

Opening the link reloads the same public page **pre-filled** with the
prior answers, in "edit" mode; submitting updates the existing
submission in place (no second row) and shows the confirmation again
(with the same link — it stays valid for repeat edits).

## URL scheme

Reuse the existing public mini-apps; the token rides as a query param so
no new server route or HTML entry is needed:

```
/e/{slug}?s={token}    event sign-up
/f/{slug}?s={token}    form
/d/{slug}?s={token}    datepoll
```

The mini-app reads `?s=`; if present it fetches the submission by token,
pre-fills, and switches submit → update. The token is globally unique
(it identifies the submission on its own); the slug just routes to the
right bundle.

## Token

- A secret `secrets.token_urlsafe(32)` (~256 bits — brute force
  infeasible), minted when the submission is created.
- **Stored hashed.** Only `sha256(token)` (hex) is persisted, in an
  `edit_token_hash` column on the submission row. The raw token lives
  only in the user's URL, so a DB dump can't reconstruct working edit
  links. (This diverges from the plaintext `LoginToken` /
  `FeedbackToken` tables; the stronger posture is warranted for a
  long-lived capability secret.)
- **Returned exactly once**, in the submit response, so the
  confirmation page can render the link. Never stored raw, never in any
  other endpoint, never recoverable — matches the "can't be recovered"
  copy.
- **Reusable, not single-use** (unlike the feedback token): the same
  link edits repeatedly. It stops working when the public page does —
  410 once the entity is archived (events: also once the event is past,
  matching the public page's own cutoff). No expiry table, no reaper:
  the hash lives on the submission row and is cascade-deleted with it.

## Data model

One nullable column per submission row — no new tables, no polymorphic
discriminator:

```
signups.edit_token_hash              text null   -- + unique partial index (where not null)
form_submissions.edit_token_hash     text null   -- + unique partial index
datepoll_submissions.edit_token_hash text null   -- + unique partial index
```

`new()` shape lives in a shared helper so the three sites can't drift:

```python
# backend/services/edit_token.py
def new_edit_token() -> tuple[str, str]:
    """Return (raw, sha256-hex). Store the hash; hand the raw to the
    client once."""
def hash_edit_token(raw: str) -> str: ...
```

One migration adds the three columns + their unique partial indexes.
Existing rows get `NULL` (their links never existed — fine).

## API

Per resource, three touch-points:

| Method | Path | Change |
|---|---|---|
| POST | `…/signups` · `…/by-slug/{slug}/submit` | mint token on create; return raw `edit_token` in the response |
| GET | `/api/v1/{resource}/by-token/{token}` | the submission's current values for pre-fill (+ the entity context the page already needs) |
| PUT | `/api/v1/{resource}/by-token/{token}` | update the submission in place |

- The by-token endpoints are **unauthenticated** — the token *is* the
  capability. Lookup is `WHERE edit_token_hash = sha256(token)`.
- `404` for an unknown/empty token; `410` when the entity is no longer
  live (archived; events also past), same predicate the public page
  uses.
- Rate-limited with `Limits.PUBLIC_SUBMIT` (GET and PUT) — token entropy
  makes brute force pointless, but cap it anyway.
- The submit response carries the raw token. Shapes:
  - Forms: `FormSubmitAck` gains `edit_token`.
  - Datepolls: the bare-201 submit now returns `{ edit_token }`.
  - Events: the sign-up response returns `{ edit_token }`.

## Per-entity edit semantics

**Forms** (simplest): `GET by-token` returns `display_name` + answers
keyed by question id, plus the `PublicFormOut` shape so the page renders.
`PUT` re-runs the submit logic against the existing submission: replace
its `FormResponse` rows (delete + re-insert from the payload) and update
`display_name`. Same per-kind validation as submit.

**Datepolls**: `GET by-token` returns `display_name` + per-date
availability/comments + the `PublicDatepollOut`. `PUT` replaces the
submission's `DatepollResponse` rows and updates `display_name`.

**Events** (non-email fields): `GET by-token` returns `display_name`,
`party_size`, `source_choice`, `help_choices` (+ the `EventOut` the page
needs). `PUT` updates those four fields on the `Signup` row with the
same validation as sign-up (e.g. `help_choices` ⊆ event's
`help_options`).

**Email cannot be edited through the link — structurally, not as a
deferral.** `EmailDispatch` carries no `signup_id` (principle #2: the
signup graph and the dispatch graph share only `Event`, never each
other). So a `Signup` reached via the edit token has **no key to its
pending email record** — there is no way to find, replace, or even
confirm the address from the submission side. Enabling email editing
would mean adding that `signup_id` link, which is exactly the
cross-reference the decoupling forbids (it would make "which signup got
which email" answerable from the schema). We will not add it. The
public edit page therefore hides the email field + email explainer in
edit mode; a respondent who needs a different email re-signs-up.

## Privacy analysis

This intentionally introduces the one thing the submission-shapes
principle (§17) called out as absent — a **read-back path from an id to
a submission**. It's safe because:

- The read-back is **capability-gated by a secret the server can't
  reproduce** (only the hash is stored). Knowing a slug, or dumping the
  DB, yields no working edit link.
- The token is **never exposed to the organiser** — it's excluded from
  every organiser/public DTO and appears only in the one-time submit
  response to the submitter. So it does not let anyone map submissions
  back to people; only the submitter, holding their own secret, can
  revisit their own submission.
- **Email is never read back or editable** (events). This isn't a
  policy choice the edit endpoint enforces — it falls out of the schema:
  `EmailDispatch` has no `signup_id`, so the `Signup` the token resolves
  to simply has no path to its pending email record. The encryption /
  wipe / no-email-to-organiser invariants are untouched, and the edit
  feature adds no new cross-link.
- `FeedbackResponse` still has no `signup_id`; nothing here adds a
  cross-link.

Static tests to add: the organiser + public list/detail DTOs never carry
`edit_token`/`edit_token_hash`; the events by-token GET response has no
email field; a tampered/absent token 404s.

## Frontend

- **Shared `EditLink.vue`** (in `public_shared/`): renders the link +
  copy button (inline `navigator.clipboard.writeText`, the public
  mini-apps' lightweight pattern) + explainer + "not recoverable"
  warning. Used by all three confirmation cards. Copy/explainer strings
  go in `public_shared/strings.ts` (`chromeStrings`) so the three read
  identically.
- Each mini-app: on mount, read `?s=`; if present, `GET by-token` →
  pre-fill state + set an `editing` flag; the submit handler targets
  `PUT by-token` instead of POST. On success, show the confirmation with
  the (unchanged) link again.
- The submit/PUT response's `edit_token` is stored in component state and
  passed to `EditLink` to build `${location.origin}${path}?s=${token}`.
- Hand-written `public_*/api.ts` types gain `edit_token` on the submit
  response + the by-token fetch/update calls.

## Migration / tests / rollout

- One Alembic migration: three nullable `edit_token_hash` columns + unique
  partial indexes; `downgrade base; upgrade head` idempotent.
- `make openapi` for the ack + by-token schema changes.
- Backend tests: mint → GET by-token pre-fill → PUT → values updated, one
  row only (per resource); wrong/absent token 404; archived entity 410;
  rate limit fires; organiser DTOs exclude the token; events edit leaves
  email + dispatches untouched.
- e2e: submit → copy link → open link → change an answer → resubmit →
  confirmation reflects the change.
- Pre-launch, no backfill. No new cron.

## Decisions taken

1. **Hashed at rest** (sha256), raw returned once. (confirmed)
2. **Events: non-email fields only** — email is *structurally*
   un-editable (no `signup_id` on `EmailDispatch`; principle #2), not a
   deferred feature. (confirmed)
3. **Reusable link, live-while-entity-is-live**, 410 when archived/past;
   no expiry table, no reaper. (confirmed)
4. **URL form** — query param `?s={token}` vs path `/…/edit/{token}`.
   See "URL form trade-offs" below. (recommendation: query param)
