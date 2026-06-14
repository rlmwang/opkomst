# Design: Datepolls

Status: proposed. Third public-facing feature after Events and Forms.
This document specifies the backend, the organiser frontend, and the
public-facing frontend. It is deliberately written to reuse the
machinery the first two features converged on; every section calls
out what is shared versus genuinely new.

## 1. What it is

A **Datepoll** is an availability poll (think Doodle). An organiser
proposes a set of candidate **slots** — each a calendar date with an
optional time range, so a slot is either a whole day or a timed
window like 19:00–21:00. Anyone with the public link picks **yes /
maybe / no** per slot by toggling it inline in a full-width month
calendar, optionally leaves a short pseudonym, and can add **one
optional note** on the whole submission. The organiser sees a results
grid and per-slot tallies to pick the winning slot. A poll with only
whole-day slots is the original dates-only Doodle — time-slots are a
pure generalisation, not a separate mode.

Non-goals (v1): time-slots within a day, respondent re-editing after
submit, account-gated voting, notifications/emails of any kind.

## 2. Naming & conventions

- Backend model: `Datepoll` (+ `DatepollDate`, `DatepollSubmission`,
  `DatepollResponse`). Router prefix `/api/v1/datepolls`.
- Public URL: `/d/{slug}` (8-char nanoid via `services/slug.py`, same
  as `/e/` and `/f/`).
- Organiser nav: a **Datepolls** top tab with **active** / **archive**
  subtabs, mirroring the Forms nav (`345e008`).
- All routes under `/api/v1/`; every mutator carries
  `@limiter.limit(...)`; all models inherit `UUIDMixin` +
  `TimestampMixin`; one Alembic migration for the schema change.
- No env defaults in code; no third-party analytics; open-source
  disclosure on the public page.

## 3. Privacy invariants

Datepolls collect **no PII and send no email**, so the encryption /
mail-lifecycle machinery is not involved at all. The invariants:

- **No email, ever.** There is no email column, no encryption, no
  dispatch rows, no cron. This feature touches none of the
  `services/mail*` or `encryption` surfaces.
- **Pseudonym is the Events contract, via a shared primitive.** The
  respondent name is `display_name: str | None`, optional,
  `max_length=100`, `NULL` = anonymous — byte-for-byte the
  `Signup.display_name` contract ("a name, real or not"). That
  contract is defined **once** as a reusable `DisplayName` annotated
  type in `schemas/common.py` (next to `LowercaseEmail`) and used by
  both `SignupCreate` and `DatepollSubmitIn`, so the pseudonym
  constraint can't drift between the two features. The frontend
  renders a localised "Anonymous" for `NULL`.
- **No hidden linkage.** A respondent's per-date answers are grouped
  by their `DatepollSubmission.id`; that row holds only the
  self-chosen pseudonym + timestamp. There is no IP, no fingerprint,
  no cookie tying a submission to a person beyond what they typed.
- **The submission id is opaque and has no read-back path.** Like the
  forms `submission_id`, nothing in the API resolves a submission id
  back to its data — there is no `GET .../submissions/{id}`. The id
  exists only to group a respondent's rows server-side; it is not
  even returned to the public client (the submit endpoint replies with
  a bare 201 — §7.1). The organiser CSV does expose it as a column,
  but that path is behind auth and read-only.
- **The public page never discloses other submissions.** A respondent
  sees only the candidate dates and their *own* toggles — never
  aggregate tallies, never another respondent's pseudonym or comment.
  (Doodle's default is the opposite; ours matches the event sign-up
  page, which never lists who else signed up.) Results are
  organiser-only, behind auth.
- **Comments are user-authored free text**, treated with the exact
  posture forms applies to `answer_text`: capped length (280),
  stored verbatim, organiser-visible only, never processed, never
  logged.
- **No PII in logs.** Routes log a route name + outcome + ids only —
  never `display_name`, never comment text.
- **Open-source disclosure on the public page**, identical copy to
  the event/form public surfaces.

There is **no wipe rule** here (nothing encrypted, no email), so the
property-based privacy state machine does not extend to datepolls.
The static `test_privacy.py` allowlists (decrypt callers, encrypt
write sites) are unaffected — datepolls import none of those modules,
which a test asserts (§13).

## 4. Lifecycle

Identical to Events/Forms: a `archived_at` soft-archive column.

- Live polls are listed on the active page; `archived_at IS NOT NULL`
  on the archive page.
- The public surface **410s** for archived or unknown slugs (same as
  Forms — no "archived but viewable" mode).
- Hard delete is refused unless the poll is archived first; it
  cascades to dates, submissions, responses via FK `ON DELETE
  CASCADE`.
- The slug is unique across the table and stays attached across
  archive/restore so bookmarked links resolve after a restore.

## 5. Data model

Four tables. SQL shown for the constraints that matter; columns
otherwise follow the mixins.

```
datepolls
  id            uuid pk
  slug          text not null unique           -- public, 8-char nanoid
  name          text not null                  -- the question, e.g. "Volgende plenair?"
  description   text null                      -- optional blurb shown on the public page
  locale        text not null default 'nl'     -- 'nl' | 'en' (Literal, drives public UI)
  created_by    text not null fk users(id) on delete set null
  chapter_id    text null fk chapters(id) on delete set null
  archived_at   timestamptz null
  created_at / updated_at
  index ix_datepolls_archived_chapter (archived_at, chapter_id)   -- mirrors forms/events list index

datepoll_slots
  id            uuid pk
  datepoll_id   text not null fk datepolls(id) on delete cascade   -- indexed
  on_date       date not null                  -- a whole calendar date, no tz
  start_time    time null                      -- both NULL = whole-day slot;
  end_time      time null                      --   both set (end > start) = timed slot
  unique (datepoll_id, on_date, start_time, end_time) NULLS NOT DISTINCT
                                                -- a slot can't appear twice; NULLS NOT
                                                -- DISTINCT makes the whole-day slot
                                                -- unique per day (PG 15+)
  -- display order is on_date ASC, then start_time (whole-day first).
  -- (on_date, start_time, end_time) is the natural key the edit diff matches on
  -- (see apply_slots, §7.1) — the editor yields slots, not row ids.

datepoll_submissions
  id            uuid pk                          -- this IS the submission identifier
  datepoll_id   text not null fk datepolls(id) on delete cascade   -- indexed
  display_name  text null                        -- pseudonym, real-or-not, NULL = anonymous
  note          text null                        -- one optional note on the whole submission
  created_at / updated_at

datepoll_responses
  id            uuid pk
  submission_id text not null fk datepoll_submissions(id) on delete cascade   -- indexed
  datepoll_slot_id text not null fk datepoll_slots(id) on delete cascade      -- indexed
  availability  text not null                    -- 'yes' | 'no' | 'maybe'
  unique (submission_id, datepoll_slot_id)        -- one answer per (respondent, slot)
  check ck_datepoll_responses_availability (availability in ('yes','no','maybe'))
```

Design notes:

- **`availability` is single-sourced**, exactly like `QuestionKind`
  from the forms hardening pass: an `Availability = Literal["yes",
  "no", "maybe"]` in `schemas/datepolls.py` is the canonical
  vocabulary, `ALLOWED_AVAILABILITY = frozenset(get_args(Availability))`
  drives validation, and a `CHECK` constraint
  (`ck_datepoll_responses_availability`, hand-written in the
  migration since Alembic doesn't autodetect CHECKs) makes a bad row
  unrepresentable.
- **A `datepoll_response` row exists only for an answered slot.** An
  unset slot for a respondent = no row (treated as "no opinion"). A
  row requires an explicit `availability`. There is no per-response
  comment: a respondent leaves **one optional `note` on the whole
  submission** (`datepoll_submissions.note`), aggregated for the
  organiser as a notes list rather than scattered per slot.
- **A slot is `(on_date, start_time, end_time)`.** Both times NULL =
  a whole-day slot (the original dates-only poll); both set
  (`end > start`) = a timed slot. A day carries either one whole-day
  slot or N timed slots — never both. `on_date`/`start_time`/
  `end_time` are naive calendar/wall values (no tz); the feature has
  no timezone subtlety like Events.
- **The submission/response split follows one rule across the app, not
  a copy of forms.** The shared rule (written up in
  `docs/principles-architecture.md`): a respondent answering a
  *fixed* attribute set gets one flat row (`Signup`); a respondent
  answering an *organiser-defined item set* gets one row per
  (submission, item) (`FormResponse`, `DatepollResponse`); a **parent
  submission row exists iff there is per-submission data to store**.
  Forms has none, so it has no parent table (and deliberately so —
  an empty parent row would be a hook to attach identity later).
  Datepolls have a pseudonym, so they get a `datepoll_submissions`
  parent — the same reason `Signup` carries `display_name`. The
  shapes differ *because the data differs*, not by accident.

## 6. Backend layout

One file per concern, mirroring Forms one-to-one.

```
backend/
  models/datepolls.py        Datepoll, DatepollSlot, DatepollSubmission, DatepollResponse
  schemas/datepolls.py       DTOs + Availability literal (the kind-enum analogue)
  services/datepolls.py      enrich / to_out / to_public_out / apply_slots /
                             slot_aggregates / submissions   (mirror services/forms.py)
  routers/datepolls.py       chapter-scoped CRUD + organiser reads
  routers/datepolls_public.py  public by-slug fetch + submit + qr.svg
  alembic/versions/...       one migration: 4 tables, enum CHECK, unique + FK cascades
```

### 6.1 Reuse (no new code)

- **Chapter scoping** — `services/access.py` is already generic
  (`get_scoped` / `scope_filter` / `list_filter`). Extend the
  `_Scoped` TypeVar to `TypeVar("_Scoped", Event, Form, Datepoll)`
  and add two one-line wrappers `get_datepoll_for_user` /
  `datepoll_scope_filter`. The 404-not-403 existence-hiding rule and
  live-membership filter come for free.
- **QR** — `services/qr.py::render_qr(target_url)` is already
  URL-keyed; the datepoll QR endpoint calls
  `render_qr(f"{PUBLIC_BASE_URL}/d/{slug}")`. Zero new QR code.
- **Slug** — `services/slug.py::new_slug()`.
- **Pseudonym primitive** — `DisplayName` annotated type in
  `schemas/common.py` (new, shared with Events; see §3). Both
  `DatepollSubmitIn` and `SignupCreate` use it, so the optional /
  `≤100` / "real or not" contract lives in one place.
- **Rate limits** — public submit reuses `Limits.PUBLIC_SUBMIT`
  (already named generically in the forms pass); CRUD uses
  `ORG_RARE` / `ORG_WRITE`; the rate-limit audit test picks the new
  mutators up automatically.
- **Diff-apply** — `apply_slots` is the `apply_questions` pattern but
  matched on the **natural key `(on_date, start_time, end_time)`**, not
  a client id: insert slots that are new, keep (and so preserve the
  responses of) slots still present, delete rows that dropped out of
  the payload (cascade takes their responses). The editor sends a set
  of slots, never row ids, so `DatepollSlotIn` carries no `id` (§7.1).
- **DTO split** — `DatepollListOut` vs `DatepollOut` (adds the date
  list + description), exactly like `FormListOut`/`FormOut`. Following
  the **Events** precedent (`EventOut.attendee_count` is a computed
  scalar, not the raw signup list), `DatepollListOut` carries
  `date_count` + `first_date`/`last_date` so a list row is useful
  without shipping every date; `enrich()` batches both the chapter
  names and the per-poll date count/range in grouped `IN` queries, so
  list endpoints never N+1.
- **Submission→CSV grouping** — folding answer rows into one dict per
  submission is the same mechanic `forms_svc.submissions()` already
  does. Extract the grouping into a small shared helper (or mirror it
  deliberately); the typed per-feature queries that feed it stay
  separate.
- **Aggregation math** — per-slot tallies are simple counts; no
  shared `ratings.py` needed, but `slot_aggregates` lives in the
  service (unit-testable without a router fixture), same as
  `forms_svc.question_aggregates`.

### 6.2 Proposed generic extractions (motivated by the 3rd copy)

Two patterns are about to exist in triplicate. The rule is "delete
the shape when you find it shaped by a previous copy," so this
feature is the right moment to extract them — done as part of this
work, not deferred:

1. **`spa.py` public-app serving.** `_serve_public_event` and
   `_serve_public_form` are near-identical. Extract
   `_serve_public_app(*, html_name, payload_marker, payload, head_meta)`
   that does the file-exists fallback, payload-inline, head-inject,
   and cache headers; the three resources each pass their
   `model_dump_json()` payload + `_og_head(...)` result. Datepoll
   adds `public-datepoll.html` + `__OPKOMST_DATEPOLL__` and a
   `_build_datepoll_head_meta` one-liner over the shared `_og_head`.
2. **Public URL helpers.** `lib/event-urls.ts`, `lib/form-urls.ts`
   are identical-shaped. Extract `lib/public-urls.ts` with
   `publicUrl(prefix, slug)` + `qrUrl(resource, slug)`; datepoll uses
   it directly and events/forms migrate to it. (Tiny, but it's the
   third copy.)

Neither extraction is required for the feature to work; both are the
"leave it cleaner" move and keep the shared surface minimal.

### 6.3 No cron

Datepolls have no email, no tokens, no expiry sweep. `cli.py` and the
reapers are untouched. (A future "auto-archive once every candidate
date is in the past" job is explicitly out of scope.)

## 7. API surface

Organiser (all `require_approved`, chapter-scoped):

| Method | Path | Returns | Limit |
|---|---|---|---|
| POST | `/api/v1/datepolls` | `DatepollOut` | `ORG_RARE` |
| GET | `/api/v1/datepolls` | `list[DatepollListOut]` | — |
| GET | `/api/v1/datepolls/archived` | `list[DatepollListOut]` | — |
| GET | `/api/v1/datepolls/{id}` | `DatepollOut` | — |
| PUT | `/api/v1/datepolls/{id}` | `DatepollOut` | `ORG_WRITE` |
| POST | `/api/v1/datepolls/{id}/archive` | `DatepollOut` | `ORG_RARE` |
| POST | `/api/v1/datepolls/{id}/restore` | `DatepollOut` | `ORG_RARE` |
| DELETE | `/api/v1/datepolls/{id}` | 204 | `ORG_RARE` |
| GET | `/api/v1/datepolls/{id}/summary` | `DatepollSummaryOut` | — |
| GET | `/api/v1/datepolls/{id}/submissions` | `list[DatepollSubmissionOut]` | — |

Public (unauthenticated, by slug):

| Method | Path | Returns | Limit |
|---|---|---|---|
| GET | `/api/v1/datepolls/by-slug/{slug}` | `PublicDatepollOut` | — |
| POST | `/api/v1/datepolls/by-slug/{slug}/submit` | `DatepollSubmitAck` (edit_token) | `PUBLIC_SUBMIT` |
| GET | `/api/v1/datepolls/by-token/{token}` | `DatepollEditOut` | — |
| PUT | `/api/v1/datepolls/by-token/{token}` | `DatepollEditOut` | `PUBLIC_SUBMIT` |
| GET | `/api/v1/datepolls/by-slug/{slug}/qr.svg` | image/svg+xml | — |

### 7.1 Key schemas

```python
Availability = Literal["yes", "no", "maybe"]

class DatepollSlotIn(BaseModel):       # create/update payload
    on_date: date                      # natural key part 1; no client id (apply_slots diffs on the triple)
    start_time: time | None = None     # both None = whole-day; both set (end > start) = timed.
    end_time: time | None = None       #   a model_validator enforces both-or-neither + end > start.

class DatepollCreate(BaseModel):
    chapter_id: str
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    locale: Locale = "nl"
    slots: list[DatepollSlotIn] = Field(default_factory=list, max_length=200)

class DatepollUpdate(DatepollCreate): ...     # distinct class for OpenAPI clarity

class DatepollListOut(BaseModel):      # list rows — scalars + computed date summary, no raw slots
    id, slug, name, locale, chapter_id, chapter_name, archived, created_at
    date_count: int                    # distinct candidate DAYS (not slots), computed in enrich (batched)
    first_date: date | None            # earliest / latest candidate day, so the row shows a range
    last_date: date | None

class DatepollOut(DatepollListOut):    # single — adds the candidate slot list + description
    description: str | None
    slots: list[DatepollSlotOut]       # {id, on_date, start_time, end_time}, sorted (day, then start)

class PublicDatepollOut(BaseModel):    # what /by-slug renders
    id, name, description, locale
    slots: list[DatepollSlotOut]

# --- public submit ---
class DatepollAnswerIn(BaseModel):
    datepoll_slot_id: str
    availability: Availability

class DatepollSubmitIn(BaseModel):
    display_name: DisplayName          # shared primitive (schemas/common.py): optional, <=100, real-or-not
    note: str | None = Field(default=None, max_length=280)   # one note on the whole submission
    answers: list[DatepollAnswerIn]

class DatepollSubmitAck(BaseModel):
    edit_token: str                    # secret edit-link token, returned once (see docs/design-edit-link.md)

# --- organiser reads ---
class DatepollSlotSummary(BaseModel):
    id: str
    on_date: date
    start_time: time | None
    end_time: time | None
    yes: int
    maybe: int
    no: int

class DatepollSummaryOut(BaseModel):
    submission_count: int
    slots: list[DatepollSlotSummary]   # in (day, then start) order
    best_slot_id: str | None           # most yes, then most maybe, then most "not filled"; no ignored
    notes: list[str]                   # submission notes, newest first

class DatepollSubmissionOut(BaseModel):    # one CSV row per respondent
    submission_id: str
    display_name: str | None
    note: str | None                   # the whole-submission note
    created_at: datetime
    answers: dict[str, str]            # keyed by datepoll_slot_id -> availability
```

Submit handler validation (same skeleton as `forms_public.submit_form`,
adapted to the parent/child shape): resolve the live poll (410 if
archived/unknown); reject any `datepoll_slot_id` not on this poll
(400); `availability` is constrained by the `Availability` literal at
the schema boundary; create one `DatepollSubmission` (with the optional
`note` + a minted edit-link token) + N `DatepollResponse` rows in one
commit; return `DatepollSubmitAck(edit_token=...)` — the raw token,
once, for the magic edit link (see `docs/design-edit-link.md`). No
required-field gate beyond "at least one answered slot" (a poll with
zero answers is a no-op — 400). Editing rides the by-token GET/PUT,
same as events/forms.

## 8. Organiser frontend

Mirrors the Forms pages and reuses every shared piece introduced so
far.

### 8.1 Composables

`composables/useDatepolls.ts` — the `useForms.ts` shape exactly:
`useDatepollList` / `useArchivedDatepolls` (typed `DatepollListOut[]`),
`useDatepoll` / `useDatepollSummary`, `fetchDatepollSubmissions`,
`usePublicDatepoll`, and the create/update/archive/restore/delete +
`useSubmitDatepoll` mutations with `["datepolls"]` cache invalidation.

`composables/useDatepollClipboard.ts` — thin wrapper over the shared
`useShareClipboard` (same as `useFormClipboard`).

### 8.2 Pages

- **`DatepollListPage.vue`** — `ListPageView` + `useChapterUrlFilter`
  (the composable extracted in the forms pass) + row card with public
  link, copy button, QR thumbnail, "details"/"archive" actions.
  Structurally the same as `FormListPage`.
- **`ArchivedDatepollsPage.vue`** — pure reuse of `useArchivedList`
  (the composable from the forms pass): `query`/`restore`/`remove` +
  `prefix: "datepolls.archived"`; only the row template is local.
- **`DatepollEditPage.vue`** — `FormPageShell` + `useFormDraft`
  (draft persistence, `datepoll-edit-draft:{id|new}`) +
  `useChapterUrlFilter`-derived chapter prefill. Sections: name,
  optional description, chapter select, image, locale select, and the
  **slot picker** — a PrimeVue `DatePicker` in `selectionMode="multiple"`
  `inline` for choosing candidate days, then **one card per chosen day**
  holding that day's time-slots: removable `start–end` pills plus an
  `+ time-slot` add-row (two native `<input type="time">`). A day with
  no time-slots stays whole-day (no label). The payload (`DatepollSlotIn`)
  emits one slot per range, or a single whole-day slot for a day with
  none; existing slots keep their id (matched on the natural key) so
  responses survive an edit.
- **`DatepollDetailsPage.vue`** — overview card (title, chapter chip,
  public link + copy, QR, edit button) identical to
  `FormDetailsPage`, plus the **results view**:
  - **Per-slot tally bars** reusing `barWidth` (`lib/format.ts`):
    three stacked counts (yes / maybe / no) per slot (date + time
    range when timed), the winning slot highlighted.
  - **Notes** — the submission notes, listed newest-first.
  - **Grid** (rows = pseudonymous submissions, columns = slots, plus a
    trailing note column): cells colour-coded yes/maybe/no.
    Horizontally scrollable for many slots.
  - **CSV export** via the shared `downloadCsv` (`lib/csv-export.ts`):
    header `name, submitted_at, {each slot}, note`, one row per
    submission; a slot column holds `yes/maybe/no`.
    Filename `${filenameSlug(name)}-${id}.csv`.

### 8.3 Nav & routing

Add the **Datepolls** tab with active/archive subtabs (copy the Forms
nav block). Client routes: `/datepolls`, `/datepolls/new`,
`/datepolls/:id/details`, `/datepolls/:id/edit`,
`/datepolls/archived`. The public `/d/:slug` is **not** an admin SPA
route — it is served by the backend mini-app (next section).

## 9. Public-facing frontend

A standalone mini-app under `frontend/src/public_datepoll/`, mirroring
`public_form/`: `PublicDatepoll.vue`, `api.ts` (bare fetch + the
`__OPKOMST_DATEPOLL__` inlined payload, no Vue Query), `i18n.ts`
(inline nl/en dictionary, `?lang=` override — the same lightweight
pattern as `public_form/i18n.ts`). Built as a separate Vite entry
(`public-datepoll.html`) and served by `spa.py` at `/d/{slug}` with
the payload inlined for first-paint and a 60 s
`stale-while-revalidate` cache window — identical mechanics to the
event/form public pages.

### 9.1 The core UX: one inline full-width month grid

The fill-out surface is a **single full-width month calendar** (one
per spanned month, stacked vertically) with the slots living **inline
in the day cells** — no separate list, no popover. All state binds to
one client-side answers map (`Record<datepoll_slot_id, Availability |
null>`).

- Render the month(s) that contain candidate slots at full content
  width, each a 7-column grid with Monday-first weekday headers.
- Non-candidate days render greyed and inert.
- A **whole-day candidate** is the day cell itself: one tri-state
  toggle (day number + colour + glyph), cycling unset → yes → maybe →
  no on tap. No "whole day" label — a dates-only poll looks exactly
  like the original.
- A **timed day** shows the day number plus a stacked **pill per
  slot**, each its own tri-state toggle labelled with the compact time
  range (`19:00–21:00` → `19–21`). State shown via colour **and** a
  glyph (not colour-only — accessibility). A compact legend sits above
  the calendar.

**Shared chrome.**

- An optional **pseudonym field**, one optional **note** input on the
  whole submission, and a **submit** button.
- States: loading → fillable → submitted ("thanks" + the magic edit
  link) → unavailable (410). Same state machine + `EditLink` as the
  other public surfaces.
- Open-source disclosure + privacy one-liner in the footer, consistent
  with the other public surfaces.

On submit the answers map is flattened to `answers:
[{datepoll_slot_id, availability}]` (dropping unset slots) and posted
with `display_name` + `note` to `/by-slug/{slug}/submit`. The ack
carries the edit token; the page shows the thank-you state and the
edit link. Reopening `?s={token}` pre-fills and PUTs (edit-while-live).

Component split: a `MonthCalendar.vue` (renders one full-width month,
draws each candidate day's slots inline, emits toggle for a slot)
reused once per spanned month; `PublicDatepoll.vue` owns the shared
answers map + note and wires submit/edit.

## 10. i18n

New `datepolls.*` namespaces in `locales/{nl,en}.json` for the
organiser pages (list / archived / edit / details, with the
`useArchivedList` suffix convention: `restored`, `restoreFail`,
`deleteOk`, `deleteFail`, `deleteConfirmTitle`, `deleteConfirmBody`,
`delete`, `loadFailed`). The public mini-app keeps its own inline
dictionary (it never loads the admin i18n bundle).

## 11. Migration

One autogenerated migration for the four tables, hand-augmented with
the `availability` CHECK and the two unique constraints (Alembic
autodetects neither CHECKs nor — reliably — composite uniques, so
verify the generated file). CI's `downgrade base; upgrade head;
upgrade head` idempotency gate covers it. `make openapi` regenerates
`openapi.json` + `schema.ts`; new `Datepoll*` types are re-exported
from `api/types.ts`.

## 12. What's shared vs new (summary)

Reused unchanged: `access.py` generics (+1 TypeVar arm, 2 wrappers),
`services/qr.py`, `services/slug.py`, `Limits.PUBLIC_SUBMIT` +
`ORG_*`, the rate-limit audit, `useArchivedList`,
`useChapterUrlFilter`, `useFormDraft`, `FormPageShell`,
`ListPageView`, `DetailsPageShell`, `useShareClipboard`,
`useGuardedMutation`, `lib/csv-export.ts`, `barWidth`,
`filenameSlug`, the `FormListOut/FormOut` + `enrich` projection
pattern, the `apply_questions` diff pattern, the `QuestionKind` +
CHECK single-source pattern, the public mini-app + payload-inline
pattern.

Shared but extracted/added by this work (so the third copy doesn't
fork): the `DisplayName` pseudonym primitive in `schemas/common.py`
(also adopted by `SignupCreate`); the submission→CSV grouping helper
(factored out of `forms_svc.submissions`); the two §6.2 generic
extractions (`_serve_public_app` in `spa.py`, `lib/public-urls.ts`,
both also adopted by events/forms); and the "submission shapes" rule
written into `docs/principles-architecture.md`.

New: 4 models + migration, `schemas/datepolls.py`,
`services/datepolls.py`, two routers, `useDatepolls.ts` +
`useDatepollClipboard.ts`, four organiser pages, the
`public_datepoll/` mini-app incl. the month-calendar tri-state
component, the nav entry, i18n.

## 13. Testing plan

Mirror the forms test files:

- `test_datepolls_router.py` — CRUD, chapter scoping (404 cross-
  chapter), archive/restore/delete-guard, list batching (no N+1),
  `DatepollListOut` carries the computed `date_count`/range but not
  the raw date list.
- `test_datepoll_slots.py` — `apply_slots` add/edit-in-place/delete-
  cascade; timed-slot round-trip + ordering; the unique
  `(datepoll_id, on_date, start_time, end_time)` (NULLS NOT DISTINCT)
  rejects dupes incl. two whole-day slots on a day; the `availability`
  CHECK rejects a bad direct insert; schema rejects inverted / half-
  open time ranges.
- `test_datepolls_public.py` — by-slug 410 on archived/unknown,
  submit happy path (returns edit_token, note stored on the
  submission), unknown-slot 400, `PUBLIC_SUBMIT` rate limit fires,
  anonymous (`display_name=null`) submission stored as anonymous.
- `test_privacy.py` extension — assert the datepoll modules import
  none of `encryption` / `mail*`, and that `DatepollResponse` has no
  email/IP column (a structural check, cheap insurance).
- e2e — organiser creates a poll with 3 dates → public votes → grid +
  tallies reflect it (the `7bb6204` forms-critical-path analogue).

## 14. Rollout

Pre-launch, no data to preserve, so: build behind the same nav
gating as Forms, ship the migration, regenerate OpenAPI. No feature
flag, no backfill, no cron registration.

## 15. Decisions taken (confirm)

1. **Name / URL:** `Datepoll` / `/d/`. (confirmed)
2. **Submit returns an edit-link token** (superseded the original
   "bare 201, no ack" decision once the magic edit link shipped across
   all three public surfaces — see `docs/design-edit-link.md`). The
   parent submission row carries the hashed token + the note; the by-
   token GET/PUT let a respondent revisit and edit while the poll is
   live. There is still no organiser-facing read-back of a submission
   id.
3. **Pseudonym = Events contract via a shared primitive:** optional,
   nullable `display_name`, `max_length=100`, `NULL` → "Anonymous" in
   the UI, defined once as `DisplayName` in `schemas/common.py` and
   used by both `SignupCreate` and `DatepollSubmitIn`. (confirmed)
6. **Submission shapes are one rule, not three copies:** flat row for
   fixed attributes (events), (submission, item) rows for organiser-
   defined item sets (forms/datepolls), a parent submission row iff
   there's per-submission data — so forms stays table-less (an empty
   parent would only invite future PII) while datepolls get one for
   the pseudonym + note. Edit-diff keys on the natural key
   (`(on_date, start_time, end_time)`), not a client id. Written up in
   `docs/principles-architecture.md`.
4. **One optional note per submission** (superseded the original
   "per (respondent, date) cell comment" decision when time-slots
   landed — a comment per slot was too noisy in the inline grid). The
   note lives on `DatepollSubmission`; the organiser sees a notes list.
5. **Public UX is one inline full-width month grid** (§9.1):
   slots live inside the day cells (whole-day = the cell itself, timed
   = a pill per slot), all bound to one answers map. (Superseded the
   original synced calendar-plus-list two-view design.)
7. **Slots, not just dates** — a candidate is `(on_date, start_time,
   end_time)`, NULL times = whole-day. A day has one whole-day slot or
   N timed slots, never both; the dates-only poll is the all-whole-day
   case. Edit-diff keys on the `(on_date, start_time, end_time)` triple.

## 16. Out of scope (future)

Auto-archive past-dated polls; per-slot capacity limits; exporting the
winning slot straight into a new Event. (Respondent edit-via-token and
time-slots, originally listed here, have since shipped.)
