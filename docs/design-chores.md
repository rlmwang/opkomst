# Design proposal — Recurring chores (Dutch: Takenroosters)

Status: proposal. A fourth organiser-owned entity alongside Event, DatePoll, and Form.

## 1. What we're building

An organiser creates a **roster** of **recurring chores**. Each chore is tied to one or
more days within a repeating **k-week cycle** — weekly by default (k=1, "every Wednesday
and Friday"), or biweekly / k-weekly (k>1, e.g. "the bins, every *other* Wednesday").
k is set once for the whole roster, and when k>1 an anchor Monday pins which calendar week
is "week A". The roster gets a public link. Anyone with the link **enrols** as a volunteer — a name (real or not),
optionally an email — and ticks the chores they're willing to do. The system then
**assigns** volunteers to concrete dated occurrences ("shifts") with a fairness rule, on
a rolling horizon. When a shift comes up, the assigned volunteer can **mark it done** or
**hand it off** ("can't make it — find someone else"), which reassigns it.

The hard parts, and where this differs from the other three entities:

- It is **interaction-heavy and long-lived**. The other three are submit-once. This one
  the same person returns to repeatedly, over weeks.
- It pulls the email question in the opposite direction. Events keep an address only to
  send *one* mail the day after, then delete it. Useful chore reminders need the address
  to **persist** for the life of the enrolment. That is a real change to the privacy
  affordance, and the bulk of this document is about doing it honestly rather than
  smuggling it in.
- Volunteers are **not organisers**. They must never need an account, a password, or an
  approval step. They get a bookmarkable personal page via the same per-submission
  edit-token mechanism the other entities already use.

## 2. First principles (the contract these decisions serve)

1. **No accounts for the public.** A volunteer's identity is a pseudonym plus a secret
   token in a URL. Same primitive as `Signup.edit_token_hash` today. An email is a
   *convenience channel*, never an identity.
2. **The roster works fully without email.** Every reminder/confirm/handoff action is
   reachable from the personal token page. Email only *pushes* you there. If you decline
   email you lose reminders, nothing else.
3. **Email is retained only as long as it is doing work, and the work is disclosed.**
   For events "doing work" lasts one day. For a roster it lasts as long as you're
   enrolled. We say that plainly on the form, and we make leaving / muting one click that
   deletes the address immediately.
4. **Decryption stays in the lifecycle worker.** The existing invariant
   (`encryption.decrypt` is called from `services/mail_lifecycle.py` and nowhere else)
   is *preserved* — all chore mail also sends from the lifecycle worker.
5. **Clean break, parallel structure.** We mirror the proven Event/Form/DatePoll shape
   for everything that is the same (CRUD, chapter scoping, archive, slugs, public
   mini-app, Vue Query composables) and only invent where the domain genuinely differs
   (recurrence, occurrence materialisation, fairness, long-lived mail). No shoehorning the
   recurring-reminder flow into `EmailDispatch`, whose entire shape is "fire once, wipe".

## 3. Vocabulary / domain model

| Name | Parallels | Meaning |
|---|---|---|
| **Roster** | Event / Form / Datepoll | Top-level organiser-owned entity. The takenrooster (task-roster) schedule. |
| **Chore** | FormQuestion / DatepollSlot | A recurring task in a roster, with a weekday set. |
| **Volunteer** | Signup / FormSubmission | A public enrolment: pseudonym, optional encrypted email, edit token. |
| **Enrollment** | (like `user_chapters`) | Junction: which chores a volunteer opted into. |
| **Shift** | (new) | A materialised `(chore, date, slot)` occurrence with an assignee and a status. |

User-facing naming: Dutch **"Takenrooster(s)"** (task roster), English **"Chores"**. Route
prefix `/chores` (admin) and `/c/{slug}` (public) — `c` is the only unused initial next to
`e`/`f`/`d`. i18n prefix `chores.`.

## 4. Standard fields we copy from the other entities

Every top-level entity shares the same spine (confirmed across `models/events.py`,
`models/forms.py`, `models/datepolls.py`). The **Roster** copies it verbatim:

| Field | Copied? | Note |
|---|---|---|
| `id` (UUID7), `created_at`, `updated_at` | ✅ | `UUIDMixin` + `TimestampMixin`, as every model. |
| `slug` (unique, indexed) | ✅ | `services/slug.py::new_slug`, bookmark-stable across archive. |
| `name` | ✅ | Roster title. |
| `description` | ✅ | Optional blurb (nullable, like Form/Datepoll). |
| `image_url` + `image_artist_instagram` | ✅ | Reuse `ImageField` + the GitHub-hosted 4:5 hero. Optional. |
| `locale` (`Literal["nl","en"]`, default `"nl"`) | ✅ | Drives public page + email language. |
| `created_by` (FK `users.id`, SET NULL) | ✅ | Organiser. |
| `chapter_id` (FK `chapters.id`, SET NULL, indexed) | ✅ | Chapter ownership / scoped access. |
| `archived_at` (nullable, indexed) | ✅ | Archive/restore (not `deleted_at`; this is an org entity). |
| `Index("ix_rosters_archived_chapter", "archived_at", "chapter_id")` | ✅ | Same list-query index pattern. |
| `reminder_enabled` (bool, default True) | ✅ | Master switch for shift reminders. |
| `location` + `latitude` + `longitude` | ✅ (optional) | Like Datepoll: optional venue via `LocationPicker`. |
| `starts_at` / `ends_at` (naive datetimes) | ❌ | Replaced by recurrence + `starts_on`/`ends_on` dates. |
| `source_options` / `help_options` | ❌ | Event-specific. |
| `feedback_enabled` | ❌ | No post-event questionnaire for a roster (could be added later). |

Roster-specific additions:

- `period_weeks : int` (k ≥ 1, default 1) — the recurrence cycle length, **set once for
  the whole roster** (every chore shares the same k). k=1 is plain weekly; k=2 biweekly;
  etc.
- `anchor_monday : Date | None` — the Monday that starts cycle index 0. **Required when
  k > 1**, ignored (and nullable) when k = 1 (a 1-week cycle has nothing to anchor).
  Validated to fall on a Monday.
- `starts_on : Date` — first date shifts may be generated. Defaults to `anchor_monday`
  when k > 1; bounds, but does not define, the periodicity.
- `ends_on : Date | None` — last date; `NULL` = open-ended (rolling horizon).
- `reminder_days_before : int` (default 1) — how many days before a shift we mail. Shifts
  are **date-only** (no clock time — a chore is "on Wednesday", not "Wednesday at 14:00"),
  so reminders can't use an hours-before offset. The reminder for a shift on `D` is sent on
  the sweep covering `D - reminder_days_before`, at a fixed civil local hour (a module
  constant, e.g. 18:00 Europe/Amsterdam) so mail never lands at midnight.

Public **Volunteer** copies the submission spine:

- `display_name` — reuse `common.DisplayName` (optional pseudonym, ≤100, whitespace→None).
- `edit_token_hash` (unique, indexed) — reuse `services/edit_token.py` (SHA-256 of the
  raw token; raw shown once, never stored). This *is* the personal-page key.
- **New:** `encrypted_email : LargeBinary | None`, `email_reminders : bool`.

## 5. Data model

```
Roster                      (organiser-owned; standard spine + recurrence bounds)
 ├─ Chore         1─N       roster_id FK CASCADE
 │    name, description?, ordinal, cycle_slots (JSON list[int], 0..7k-1),
 │    people_per_shift (int, default 1), emoji? (optional, EmojiPicker)
 ├─ Volunteer     1─N       roster_id FK CASCADE
 │    display_name?, encrypted_email?, email_reminders, edit_token_hash (unique)
 │    └─ Enrollment  N─N    composite PK (volunteer_id, chore_id), CASCADE both
 └─ Shift  (materialised occurrence)
      chore_id FK CASCADE, on_date Date, slot_index int,
      volunteer_id FK SET NULL (assignee; NULL = open / needs pickup),
      status Literal['scheduled','done','open','missed'] CHECK,
      done_at?, reminder_sent_at?
      UniqueConstraint(chore_id, on_date, slot_index)
```

Decisions baked into the shape:

- **Recurrence as a cycle-slot set: `cycle_slots : JSON list[int]` on the Chore**, not a
  child table. Each slot is a flat offset into the k-week cycle: `offset = week_index*7 +
  weekday`, range `0 .. 7*period_weeks - 1`, Mon=0 (Python `date.weekday()`). So for k=2,
  "every other Wednesday in week A" is `[2]`, "every Wednesday" is `[2, 9]`, "Mondays in
  week B" is `[7]`. For k=1 this collapses to the plain weekday set `0..6`. Matches the
  existing JSON-list idiom (`help_options`); the set is small and read-whole.
  Each value is validated `< 7 * roster.period_weeks`; shrinking k drops out-of-range
  slots (see frontend, §10).
- **Shifts are materialised, not computed.** They must carry per-occurrence state
  (assignee, done, handoff), so they have to be rows. A cron generates them on a rolling
  horizon (default 28 days ahead) up to `ends_on`.
- **One Shift = one person's duty.** A chore needing two people on a date
  (`people_per_shift = 2`) produces two Shift rows with `slot_index` 0 and 1. Keeps
  assignment, reminders, and handoff per-person and avoids an assignee join table.
- **`volunteer_id` is `ON DELETE SET NULL`.** When a volunteer leaves we hard-delete the
  Volunteer (and their email goes with it), past shifts keep `status='done'` with a null
  assignee so completion stats survive anonymously; future `scheduled` shifts flip to
  `open` and get reassigned on the next tick.
- **`status='open'`** is the "up for grabs" state: unassigned and visible to all
  volunteers to claim from their personal page.

## 6. The email / privacy decision (the crux)

This is the one place we knowingly diverge from the events contract, so it gets the most
care. Today (`models/email_dispatch.py`, `services/mail_lifecycle.py`, and the three
privacy tests) the rule is: an attendee address is encrypted into a `PENDING`
`EmailDispatch` row at signup, decrypted once by the worker, and the ciphertext is nulled
*atomically with* the terminal status flip. The asserted invariant is
`encrypted_email IS NULL ⇔ no PENDING dispatch`. That whole machine is built around
**"use once, then it must be gone."**

A roster needs the opposite: **retain the address, encrypted, for the life of the
enrolment, and reuse it every week.** Forcing that into `EmailDispatch` would corrupt the
events invariant (a never-finalising "pending" row that intentionally keeps its
ciphertext forever). So we **don't**. Chores get their own honest, separately-tested
contract:

**The chore email contract**

1. Email is **optional** on enrolment. The roster is fully usable without it.
2. If given, the plaintext is used **immediately and transiently** at enrolment to mail
   the personal-page link (`services/mail.py::send_email`, fire-and-forget, plaintext
   `to=` — exactly how organiser magic-links already work), then stored **encrypted**
   (`encryption.encrypt`) on `Volunteer.encrypted_email`. The router never holds it longer
   than the request.
3. It is decrypted **only** by the lifecycle worker, only to send a shift reminder. The
   existing decrypt-allowlist invariant is preserved unchanged.
4. It is **deleted immediately** when any of these happen:
   - the volunteer clicks "remove me" (Volunteer row deleted → email gone);
   - the volunteer toggles reminders off (`encrypted_email` nulled, `email_reminders =
     false`, enrolment kept and still assignable);
   - the roster is archived and a grace window passes, or is hard-deleted (CASCADE).
5. **Disclosure is on the form, in front of the email field**, not buried. Reuse the
   `Disclosure` component (the events page already uses it for "what do you do with my
   email?") with chore-specific copy: *"If you add your email we keep it, encrypted, for
   as long as you're on this roster, only to remind you of your turns. Remove yourself or
   switch reminders off any time and we delete it on the spot."* Every reminder email
   carries one-click **manage / mute / leave** links to the personal page. This keeps the
   open-source-disclosure and no-tracking invariants intact and extends the
   "privacy-is-in-front-of-the-form" UX principle.

**Invariants to add (and tests to write), mirroring `tests/test_privacy.py` style**

- Scope the existing wipe-rule test to events explicitly (it is about `EmailDispatch`,
  which chores do not touch).
- Extend the `encryption.encrypt` caller allowlist from `{signups.py, seed.py}` to add
  the chore enrolment router. Extend the `encrypted_email` *write*-site allowlist
  similarly. Keep the list tight — these are the only new writers.
- `encryption.decrypt` allowlist stays **exactly** `{mail_lifecycle.py}`. No new entry.
- New positive invariant: *a Volunteer with `email_reminders = false` has
  `encrypted_email IS NULL`* — the mute path must wipe, asserted by a small state test
  parallel to `test_email_state_machine.py`.
- New negative invariant: the organiser-facing volunteer list endpoint returns
  `display_name` + enrolled-chore names + per-volunteer load only — **never** email,
  ciphertext, or token (same shape rule the signup-list test enforces).

## 7. Lifecycle: generation, fairness, reminders, handoff

### Generation + assignment ("roster tick", daily cron)

`python -m backend.cli roster-tick` does three things per live (non-archived) roster:

1. **Extend** shifts: for every chore, for each date `D` in `[max(today, starts_on),
   today+HORIZON]` (capped by `ends_on`) that **falls in the cycle** and has no Shift row
   yet, create `people_per_shift` Shift rows (`status='open'`). Cycle membership:
   - k = 1: `D.weekday() in cycle_slots`.
   - k > 1: `offset = (D - anchor_monday).days % (7 * period_weeks)` (skip if
     `D < anchor_monday`); include iff `offset in cycle_slots`.

   The `% (7k)` math is why the anchor must be a Monday and why k is roster-wide: every
   chore reads the same cycle origin, so "week A / week B" means the same calendar weeks
   across the whole roster.
2. **Assign** every `open` shift in the horizon to an eligible volunteer (one enrolled in
   that chore) using the fairness rule below; on success `status='scheduled'`.
3. **Reconcile the past**: shifts with `on_date < today` still `scheduled` flip to
   `missed` (drives a "completion rate" stat and nudges fairness next round).

### Fairness rule (v1: greedy least-loaded, random tie-break)

For each shift to assign, among volunteers enrolled in that chore:

- compute `load` = count of their `scheduled` + `done` shifts in this roster;
- pick uniformly at random among those with the **minimum** load;
- soft constraints applied as tie-breakers / filters when alternatives exist: don't give
  one person two shifts the same day; avoid the immediately-preceding occupant of the same
  chore.

This is simple, explainable ("everyone does roughly the same number, ties drawn fairly"),
and stable: re-running the tick never reshuffles already-`scheduled` future shifts (we
only fill `open` ones). Backend Python may use `random` freely. The function is pure over
its inputs (eligible set + current loads), so it is unit-testable with a seeded RNG. Two
alternatives I deliberately did **not** pick for v1: pure random (clusters unfairly) and
strict round-robin (brittle when enrolments change mid-roster). Documented so we can swap
later behind the same function boundary.

### Reminders (hourly cron, lifecycle worker)

`python -m backend.cli dispatch chore-reminder` → new
`mail_lifecycle.run_chore_reminders()`. It selects shifts where: `on_date -
reminder_days_before` has been reached (and the day's fixed send hour has passed);
`status='scheduled'`; `reminder_sent_at IS NULL`; an assignee exists with `encrypted_email`
not null and `email_reminders` true; the roster is live with `reminder_enabled`. For each
it **decrypts in the worker**, sends `chore_reminder.html` (deep-linked to the shift on the
personal page), and stamps `reminder_sent_at`. Idempotency is the timestamp — *no ciphertext
wipe*, because retention is the whole point. On send failure we leave `reminder_sent_at`
null to retry next sweep. This reuses `send_with_retry` and the render / backend /
Message-ID plumbing in `services/mail.py` untouched.

Why a parallel function and not a third `EmailChannel`: the `CHANNELS` table keys
everything off `EmailDispatch` rows + Event-time window predicates + the encrypt-then-wipe
dispatch lifecycle. Chore reminders have none of those (no dispatch row, address persists,
window is per-Shift). A separate, smaller worker entry point is the clean fit and keeps
`CHANNELS` honest.

### Handoff / "can't make it"

From the personal page, on an upcoming `scheduled` shift the volunteer hits "find someone
else". The shift flips to `open` and is immediately re-assigned by the same fairness
function, excluding the person who bailed; if no one else is eligible it stays `open` and
shows as "up for grabs" on every volunteer's page (and, optionally later, a broadcast
mail). "Mark done" sets `status='done'`, `done_at=now`. Both are ordinary authenticated-
by-edit-token `PUT`s on the public router.

## 8. Auth for volunteers — no accounts

We reuse the **per-submission edit token** that `Signup`/`FormSubmission`/
`DatepollSubmission` already carry, via `services/edit_token.py::new_edit_token()` →
`(raw, hash)`. On enrolment we store the hash, return the raw once, and render it as a
bookmarkable URL with the existing `EditLink` component: `/c/{slug}?s={raw}`. The personal
page is the single hub: edit enrolled chores, see upcoming assigned shifts, mark
done / hand off, claim `open` shifts, manage reminders, leave. If an email was given, the
same link is mailed at enrolment (so it's recoverable from the inbox) and every reminder
links back to it. No JWT, no `User` row, no approval. The organiser JWT/RBAC path
(`auth.py`, `access.py`) is untouched and used only for the admin CRUD side.

## 9. API surface

Organiser side (`routers/chores.py`, all under `/api/v1/`, every mutator
`@limiter.limit(...)`, all scoped through new `access.get_roster_for_user` /
`access.roster_scope_filter` mirroring the Event helpers):

```
POST   /chores                              create (Roster + nested Chores)
GET    /chores                              list (chapter-scoped, active)
GET    /chores/archived                     archived list
GET    /chores/{id}                         single (for edit prefill)
PUT    /chores/{id}                         update (Roster + reconcile Chores)
POST   /chores/{id}/archive | /restore      archive / restore
DELETE /chores/{id}                         hard-delete (archived only)
GET    /chores/{id}/volunteers              roster of volunteers + load (NO email)
GET    /chores/{id}/schedule                upcoming shifts + assignees + completion stats
```

Public side (`routers/chores_public.py`, no auth):

```
GET  /chores/by-slug/{slug}                 PublicRosterOut (chores, locale, hero) — 404 if archived
POST /chores/by-slug/{slug}/enroll          {display_name?, email?, email_reminders, chore_ids[]}
                                            → EnrollAck{edit_token}
GET  /chores/by-token/{token}               personal page payload: enrolled chores,
                                            my upcoming shifts, open shifts, reminder state
PUT  /chores/by-token/{token}               edit enrolment (chores, reminders, display_name)
POST /chores/by-token/{token}/shifts/{shift_id}/done
POST /chores/by-token/{token}/shifts/{shift_id}/handoff
POST /chores/by-token/{token}/shifts/{shift_id}/claim     (take an `open` shift)
POST /chores/by-token/{token}/leave         delete volunteer + email
```

Schemas in `schemas/chores.py` reuse `common.DisplayName`, `common.LowercaseEmail`,
`Locale`, `InstagramHandle`. (`Locale` currently lives in `schemas/events.py`; task 02
relocates it to `common.py` first — it's a shared primitive.) `make openapi` regenerates
`schema.ts` (CI gate).

## 10. Frontend

Mirror the isomorphic four-page set; the agents confirmed all three entities are
structurally identical and differ only in domain fields.

**Admin pages** (lazy routes added to `router/index.ts`, `requiresAuth+requiresApproved`):

- `/chores` → `ChoresListPage.vue` via `ListPageView` (chapter filter + search + "+ New").
- `/chores/archived` → `ArchivedChoresPage.vue` via `useArchivedList`.
- `/chores/new` & `/chores/:id/edit` → `ChoresEditPage.vue` via `FormPageShell` +
  `useFormDraft` (it's a long form) + `ChapterPicker` + `ImageField` + optional
  `LocationPicker` + the **recurrence controls** (k + anchor Monday, §below) + a
  **Chore editor list**.
- `/chores/:id/details` → `ChoresDetailsPage.vue` via `DetailsPageShell`: overview card,
  chore list, volunteer count + per-volunteer load (fairness at a glance), upcoming
  schedule, completion rate, share link + QR via a new `useChoresClipboard`.
- Add **"Takenroosters"/"Chores"** as the fourth item in the workspace dropdown I just built in
  `AppHeader.vue` (`header.chores` key, `isActive` on `/chores`).

**Public mini-app** `public-chore.html` + `src/public_chore/PublicChore.vue` (new Vite
entry-point, backend-served with inlined `window.__OPKOMST_CHORE__`), reusing
`PublicShell` + `PublicHero` + `Disclosure` + `EditLink` + `PublicNotice`. Two modes off
`?s={token}`: **enrol** (pseudonym, optional email + reminders toggle behind the
disclosure, checkbox list of chores) and **personal** (enrolled chores editable, "my
upcoming turns" with Mark done / Can't make it, "up for grabs" list to claim, manage
reminders, leave).

**Composables** `useChores.ts` — the exact Vue Query pattern from `useEvents.ts`:
query keys `["chores","active",{chapter}]` / `["chores","archived",{chapter}]` /
`["chores","single",id]` / `["chores",id,"schedule"]`; mutations with optimistic
`onMutate` snapshot + `onError` rollback + `onSettled` invalidate. Plus `usePublicChore`
for the mini-app and `useChoresClipboard` wrapping `useShareClipboard`.

**Components to reuse as-is:** `ListPageView`, `FormPageShell`, `DetailsPageShell`,
`AppCard`, `SearchInput`, `AppSkeleton`, `ChapterPicker`, `LocationPicker`,
`useArchivedList`, `useGuardedMutation`, `useFormDraft`, `useShareClipboard`, `PublicShell`,
`PublicHero`, `Disclosure`, `EditLink`, `PublicNotice`, `EmojiPicker` (per-chore icon).

**Cross-cutting DRY refactors (extract → migrate the existing three → chores reuses).**
A fourth entity is the moment to pay down the copy-paste across Event/Form/Datepoll. Each
is its own task (`docs/tasks/chores/`), guarded by *no behaviour change + existing tests
pass unedited*:

- **R1 — `OrgEntityMixin`** (backend): the ~8-column spine (slug/name/image/locale/
  created_by/chapter_id/archived_at) is re-declared in all three models (~65 dup lines).
  One mixin; the composite `ix_*_archived_chapter` Index stays per-model. Schema-neutral
  (autogenerate must be empty).
- **R2 — archivable CRUD helper** (backend): the archive/restore/delete handlers are ~98%
  identical (~150 dup lines). `services/crud.py::archive/restore/hard_delete`; routers keep
  access lookup + projection only.
- **R3 — `createEntityCrud({resource})`** (frontend): `useEvents/useForms/useDatepolls` are
  ~80% identical. One factory generates list/archived/single/create/update/archive/restore/
  delete with the optimistic pattern baked in; each entity keeps only its extras. `useChores`
  becomes ~30 lines.
- **R4 — `public_access.resolve_by_slug` / `resolve_by_token`** (backend): the public
  slug + edit-token lookups (with the 404/410 guards, events-only `ends_at` check) are
  ~90% identical across the three public routers. Two helpers; chores' token-heavy personal
  page is the biggest beneficiary.
- **`ImageField`** is already reusable: `resource` is a plain `string`,
  `useImageUpload(resource)` is generic, and `image_svc.replace_entity_image(folder=...)`
  is shared by forms/datepolls — so chores just passes `resource="chores"` and the chore
  image endpoint (task 02) calls the helper with `folder="chores"`. (Identifier stem is
  `chore`/`chores` everywhere user- and URL-facing; `Roster` is the internal model name.)

**New chores-specific components (the genuinely net-new UI):**

- **Extract the "ordered array of sub-editors with add / move-up / move-down / delete"
  pattern** (task 03). `FormEditPage` + `QuestionEditor` implement it for questions;
  `DatepollEditPage` re-implements it for slots; Chores is the third. Pull it into a
  `useOrderedList` composable and build the new `ChoreEditor` (chore name + the cycle picker
  + `people_per_shift` + optional emoji) on top of it.
- A **`CycleGridPicker`** (new) — the recurrence selector. It takes `period_weeks` (k) and
  v-models the chore's `cycle_slots` (`int[]`). It renders **k rows × 7 day-toggles**
  (Mon..Sun), each row labelled "Week 1 … Week k"; for k=1 it is a single weekday row, so
  it degrades to the plain picker. Built on PrimeVue `ToggleButton`/`SelectButton`. Each
  toggle maps to the flat offset `week*7 + day`. ~60 lines, reusable.

**Recurrence controls (roster-level, top of the edit page).** `period_weeks` is a single
control for the whole roster (a stepper/select, k = 1..N) and, **shown only when k > 1**, a
required **anchor-Monday** date picker constrained to Mondays (disabled-with-reason if not
a Monday, per the UX principle). Because k is roster-wide, changing it reshapes every
`CycleGridPicker` at once: growing k adds empty week-rows; shrinking k drops slots whose
offset is now `≥ 7k` (warn-toast naming the affected chores, then clear — no silent data
loss, no stale out-of-range slots). The anchor + k together are the only inputs that make
"week A vs week B" mean a concrete calendar week, so they live above the chore list, not
per chore.

All visible strings via `t()` in `nl` + `en` (locked-step, CI fails on drift), per the UX
principles.

## 11. Cron / CLI

Two new one-shot subcommands (Coolify scheduled tasks, matching the existing cadence
style in `cli.py`):

- `roster-tick` — **daily**: extend + assign + reconcile shifts (§7).
- `dispatch chore-reminder` — **hourly**: send due shift reminders (§7).

Reaping: extend the existing post-archive purge so an archived roster's volunteer emails
are deleted after the grace window (reuse the `reap-expired` daily slot). Hard-delete
cascades clean up everything.

## 12. Tests / invariants to add

- `tests/test_privacy.py`: scope the dispatch wipe-rule assertion to events; widen the
  `encrypt` + `encrypted_email`-write allowlists to include the chore enrolment router;
  keep `decrypt` allowlist = `{mail_lifecycle.py}` exactly; add the volunteer-list
  "no email/ciphertext/token leaks" check.
- New `tests/test_chore_email_state.py` (table-test in the spirit of
  `test_email_state_machine.py`): enrol-with-email → ciphertext present; mute → ciphertext
  null, enrolment kept; leave → row gone; archive+purge → ciphertext gone.
- `tests/test_chore_fairness.py`: the assignment function over crafted enrolment/load sets
  with a seeded RNG — equal loads, tie distribution, exclusion on handoff, no double-day.
- `tests/test_chore_recurrence.py`: the cycle-membership function — k=1 weekday match; k>1
  modulo-`7k` anchoring (biweekly hits alternating weeks), dates before the anchor
  excluded, `cycle_slots` validated `< 7k`, anchor-must-be-Monday rejected otherwise.
- Router/access tests mirroring the Event suite (chapter scoping, 404-not-403, archive →
  410 public, rate-limit-on-every-mutator audit picks up the new routes automatically).
- Alembic: one autogenerated migration; CI's `downgrade base; upgrade head; upgrade head`
  idempotency check applies.

## 13. Build order (suggested)

1. Models + migration (Roster, Chore, Volunteer, Enrollment, Shift) + `access` helpers.
2. Organiser router + schemas + `make openapi` + admin pages (CRUD parity first — this is
   pure pattern-copy and gets the entity visible).
3. Public mini-app: enrol + personal page + edit-token wiring.
4. `roster-tick` (generation + fairness) + schedule view on the details page.
5. Email: enrolment link mail, `chore_reminder.html`, `run_chore_reminders`, the new
   privacy tests, the cron entries.

Stages 1–3 deliver a working, no-email roster (volunteers enrol and self-manage via the
token page); 4 adds automatic fair assignment; 5 layers on the optional, disclosed email
reminders. Each stage is independently shippable and testable.

## 14. Decisions (locked)

1. **Email** — optional, with full retention: kept encrypted for the life of the
   enrolment (§6), powering the enrolment link and recurring shift reminders, deleted
   immediately on leave / mute / roster-delete, disclosed in front of the field.
2. **Confirm / handoff** — the personal token page is the **single hub**. No one-click
   action links in emails; reminders deep-link to the page, which carries the buttons.
   Fewer secret-bearing URLs minted, and the flow works with no email at all.
3. **Fairness** — greedy least-loaded with random tie-break (§7). Pure over its inputs,
   seed-testable, stable across re-runs.
4. **Multi-person chores** — `people_per_shift` ships defaulting to 1 (one Shift row per
   occurrence), with the schema and assignment designed for N from day one.
