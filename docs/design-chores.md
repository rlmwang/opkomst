# Design proposal — Recurring chores (Dutch: Takenroosters)

Status: proposal, revised. A fourth organiser-owned entity alongside Event, DatePoll,
and Form.

> **Revision note (scheduling model).** The original design (see §7 as first written)
> eagerly materialised every occurrence into a `Shift` row on a fixed 28-day horizon and
> assigned them with a greedy, unseeded-random rule. That has two defects we are now
> fixing: (a) editing the roster (start date, cycle length, cycle slots) silently
> *diverges* from already-materialised rows, because generation is additive and never
> prunes; (b) assignment is non-deterministic in production and cannot be projected
> beyond the horizon, so volunteers cannot see or trust what is coming. The revised model
> (§7) treats occurrences as a **deterministic projection** of the pattern, keeps `Shift`
> rows only as a **sparse overlay** of state, and pins a **configurable commit horizon**
> within which the schedule is reliable. This serves three requirements directly: a
> volunteer always knows what they are expected to do, it feels fair, and a new volunteer
> is folded into the real schedule within a bounded, tunable time.
>
> A second revision replaced that model's assignment rule. The original per-date
> weighted-rendezvous hash scored every date independently, which made one volunteer's
> turn dates an i.i.d. sample: ~20% back-to-back turns and month-long droughts at typical
> pool sizes, and a ledger weight whose effect was polynomial in pool size instead of
> proportional. §7 now assigns by a **virtual-time fair rotation** (stride scheduling): a
> pure date-ordered fold that spaces turns evenly, honours materialised history, and makes
> weights mean exactly their share.

## 1. What we're building

An organiser creates a **roster** of **recurring chores**. Each chore is tied to one or
more days within a repeating **k-week cycle** — weekly by default (k=1, "every Wednesday
and Friday"), or biweekly / k-weekly (k>1, e.g. "the bins, every *other* Wednesday").
k is set once for the whole roster, and when k>1 the cycle anchors on the Monday of the
week the roster's `starts_on` falls in (derived, never stored), so "week 1" is the week the
roster begins and means a concrete calendar week across the whole roster. The roster gets a public link. Anyone with the link
**enrols** as a volunteer (a name, real or not, optionally an email) and ticks the chores
they're willing to do. The system then **assigns** volunteers to concrete dated
occurrences ("shifts") with a deterministic fairness rule. Assignments are a *projection*
of the pattern that anyone can see arbitrarily far ahead; only a near-term **commit
horizon** is pinned and reliable. When a shift comes up, the assigned volunteer can **mark
it done**, **pass** it ("can't make it, find someone else"), or **cover** someone else's,
each of which is recorded and fed back into future fairness.

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
- `starts_on : Date` — first date shifts may be generated, and (for k > 1) the **derived
  cycle anchor**: cycle week 0 runs from the Monday of the week `starts_on` falls in
  (`recurrence.cycle_anchor_monday`, computed, never stored). There is no separate anchor
  field; one date does both jobs. The start date is always inside week 0, so a weekday
  ticked in the grid's first row means the one in the week the roster begins.
- `ends_on : Date | None` — last date; `NULL` = open-ended.
- `commit_horizon_days : int` (default e.g. 21) — how far ahead the schedule is **pinned
  and reliable** (§7). Occurrences within `[today, today + commit_horizon_days]` are
  materialised and never reshuffled; beyond it the schedule is a tentative projection.
  This is the single knob that trades *stability* (long horizon: volunteers can plan far
  ahead, but edits and new volunteers take longer to take effect) against *responsiveness*
  (short horizon: the roster adapts fast, but only the near term is guaranteed). Must be
  `≥ reminder_days_before` so every reminded shift is already pinned.
- `activated_at : datetime | None` — the roster lifecycle gate (§7, "Bootstrap"). `NULL` =
  **forming** (still gathering volunteers; the schedule is an all-tentative draft that
  reflows freely and *nothing is pinned or promised*). Set = **running** (the organiser has
  pressed "Start roster"; from here the tick pins the commit horizon and reminders fire).
  One-way: a roster that has started does not fall back to forming.
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
- **Occurrences are projected; Shifts are a sparse overlay.** An occurrence
  `(chore, date, slot)` is a pure function of the pattern (`recurrence.occurs_on`), so it
  needs no row to *exist*. A `Shift` row exists only once an occurrence acquires **state**
  that the pattern cannot derive: it has been pinned into the commit horizon (assigned),
  reminded, marked done, passed, covered, or missed. This is the calendar RRULE +
  per-instance-override model (RFC 5545). The natural key `(chore_id, on_date, slot_index)`
  is itself derivable from the pattern, so an overlay row slots back into the projection
  unambiguously. Consequences: editing the pattern cannot corrupt un-materialised future
  occurrences (there is nothing to corrupt), lookahead is unbounded, and the table grows
  with *activity*, not with time. See §7 for the three timeline zones and the pinning rule.
- **One Shift = one person's duty.** A chore needing two people on a date
  (`people_per_shift = 2`) produces two Shift rows with `slot_index` 0 and 1. Keeps
  assignment, reminders, and handoff per-person and avoids an assignee join table.
- **`volunteer_id` is `ON DELETE SET NULL`.** When a volunteer leaves we hard-delete the
  Volunteer (and their email goes with it). Past overlay rows keep their outcome
  (`done`/`missed`) with a null assignee so completion stats survive anonymously. Their
  pinned future shifts inside the commit horizon are reassigned immediately (they are a
  reliable promise someone must now cover); beyond the horizon nothing was materialised, so
  the projection simply stops handing them occurrences (§7, incident table).
- **`status='open'`** is the "up for grabs" state: an occurrence that was pinned but has no
  assignee (nobody eligible, or the assignee passed and no cover was found), visible to all
  volunteers to claim from their personal page.
- **The favour-credit ledger is derived, not a new table.** "Who covered for whom / who
  passed / who inherited a departed volunteer's slot" is captured append-only in
  `ShiftEvent`, whose `kind` records the **provenance** of each holding (regular `assigned`
  vs pickups `claimed`/`covered`/`inherited`; plus `deferred`/`completed`/`missed`). The
  fairness weight (§7) folds that log into a per-volunteer net-credit at read time, and the
  same log drives the accountability display's regular-vs-picked-up split (§7 "Event log,
  favour ledger, and accountability"). One source of truth, no second table to sync.

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

## 7. Lifecycle: projection, fairness, commit horizon, reminders, actions

The scheduling model rests on one split: **an occurrence's date is a deterministic
function of the pattern; its assignment is a deterministic function of the pattern, the
current volunteer set, the favour ledger, and the assignment history so far.** Both are
therefore *projectable* to any future date: the projection is one pure fold over plain
values (the pattern's occurrences, the eligible sets, the weights, and the shifts that
already exist). We only persist a `Shift` row when an occurrence enters the reliable
near-term window or someone acts on it.

### The three timeline zones

Every occurrence sits in exactly one zone relative to `today`:

| Zone | Range | Materialised? | Behaviour |
|---|---|---|---|
| **Frozen past** | `on_date < today` | Yes (rows) | Immutable history. Outcome recorded (`done`/`missed`/passed/covered). Stats read here. Never recomputed, never pruned. |
| **Commit horizon** | `today … today + commit_horizon_days` | Yes (rows, "pinned") | The **reliable, promised** schedule. Assignments are frozen and will not reshuffle. Reminders fire here. All volunteer actions happen here. This is "your confirmed turns". |
| **Projection** | `> today + commit_horizon_days` | No | Computed on demand from pattern + volunteers + ledger + materialised history. **Tentative**: reshuffles freely and *correctly* as the roster is edited, volunteers join/leave, or the ledger moves. Shown as "likely, may change". |

The zones move: each day the commit horizon's leading edge advances by one day, and the
occurrences it crosses are **pinned** (materialised from the projection and frozen). That
daily crossing is the only place a projected assignment becomes a promise.

### Deterministic assignment (virtual-time fair rotation)

Assignment is a **date-ordered fold** in the family of stride scheduling / weighted fair
queueing (the smooth round-robin of OS schedulers and load balancers). Every volunteer
carries a **virtual time** `V`: how much of the roster they have already carried, scaled
by their weight. Occurrences are walked in date order, and each slot goes to the volunteer
with the lowest clock, whose clock then advances:

```
winner       = argmin (V[v], v)   over eligible, same-day-free volunteers
V[winner]   += 1 / weight(winner)
```

An occurrence that already has a materialised answer — a frozen past shift or a pinned
row, whatever its provenance (tick-assigned, claimed, covered, organiser hand-over) — is
never recomputed: the fold simply advances its actual assignee's clock and moves on.
History is an **input** to the fold, never an output.

**The fold is a pure function, stated precisely (so we can test it and reason about it).**
Its result depends on *only* these inputs:

1. the dated occurrences (`chore_id, on_date, slot`), in date order;
2. the **fixed** assignments — the already-materialised `(occurrence → assignee)` pairs;
3. the eligible **set** per chore (enrolled *and* available per date);
4. a per-volunteer **weight** (default `1.0`, the ledger's only channel in).

It depends on **nothing else**: not `today`, not the database, not the wall clock, not an
RNG, not iteration order (ties on `V` break by `volunteer_id`). The input surface is
larger than a per-date rule's — that is all; purity, determinism, and reproducibility
across machines are identical. All impure work (reading rows into the fixed map, resolving
`enrolled ∩ available`, folding the ledger into weights) stays in the thin shell.

Properties, each asserted in tests:

- **Projectable.** Fold from the roster's start to any future date; "who is on, three
  months out" is one linear walk over plain values.
- **Well-spaced by construction.** Lowest-clock-first is a rotation: on equal weights,
  counts stay within one turn of each other and the gap between one person's turns
  concentrates at one rotation length. Repeats before a full rotation happen only when
  the pool is too small to avoid them. (The previous per-date hash made turn dates an
  independent sample — ~20% back-to-back pairs and four-month droughts at `L = 4` were
  *expected*. That is what this replaces.)
- **Proportional weights.** A volunteer at weight `w` receives `w / Σw` of occurrences —
  `0.5` literally means half a share. (Under the multiplicative hash the effect was
  polynomial in pool size: weight 0.5 in a pool of 6 drew 0.5% of turns, not 9%.)
- **Prefix-consistent.** Folding `[a, c]` equals folding `[a, b]` and continuing over
  `(b, c]` from the resulting state. This is the invariant the pinning model needs:
  pinning day-by-day (the tick) and projecting the whole window (the outlook) are the
  same computation, so confirmed and outlook read one oracle.
- **Self-levelling.** `V` is global per volunteer, so the rotation spaces one person's
  turns across *all* chores and converges total load roster-wide; and someone who just
  covered three shifts carries a high clock, so the fold rests them automatically while
  the ledger separately settles the long-run favour.

**Same-day de-collision.** Slots of one date are picked in scarcity order (fewest
eligible volunteers first, then `chore_id`), each pick excluding volunteers already busy
that date; a refill pass admits busy volunteers rather than leaving a slot open (never
twice on the same chore). Nobody draws two chores on one day while another eligible
volunteer is free, and a slot goes unfilled only when no eligible volunteer remains —
coverage beats strict no-collision. The single-shift re-cover path (`reassign_shift`,
used when a volunteer is removed) ranks by the same folded clocks and prefers a volunteer
free that day.

**What the rotation deliberately does *not* promise: a churn-free tentative outlook.**
The rendezvous hash moved only ~`1/(L+1)` of future dates on a join; a rotation
reshuffles the tentative sequence downstream of any membership or pattern change. That
trade is intentional: everything actually promised is pinned and never reshuffles, the
outlook is explicitly labelled "may change", and a newcomer's fold-in stays bounded
(below). Even spacing and proportional shares are the product promise; far-outlook
stability is not.

### Fairness (proportional share + a favour ledger)

`weight(v)` is where long-run fairness lives:

- **Default equal weight** gives every eligible volunteer an equal share — not merely in
  expectation but by rotation: the fold always picks whoever has carried least, so counts
  stay within a turn of each other and turns are evenly spaced.
- **The favour ledger tilts the weight** so realised imbalance self-corrects. Covering a
  shift or doing extra earns credit; passing or being covered spends it. `weight(v)` is a
  bounded function of net credit, and shares are **proportional** to weight, so the clamp
  `[0.5, 2.0]` means what it says: the most-credited volunteer carries half a share, the
  most-indebted double. The ledger sets the *rate*; the rotation keeps whatever the rates
  are evenly spaced.

This is the reconciliation of "predictable" and "feels fair": the far projection is a pure
function of current state + history (predictable *given* those, self-correcting as the
ledger moves), while the commit horizon is frozen. The fairness function stays **pure over
its inputs**, so it is exhaustively unit-testable without any RNG seed.

### Folding in new volunteers (bounded, predictable)

A volunteer who enrols today immediately starts winning their fair share in the
**projection**. Their clock is seeded at the pool's current minimum `V` — caught up, owed
nothing and owing nothing — so they win turns at their fair *rate* from day one (first
turn within about one rotation) instead of being flooded with back-pay. They do not
appear in the already-pinned commit horizon (those promises stand). They begin receiving
*real* pinned turns as the horizon's edge rolls past them,
i.e. **within `commit_horizon_days`** at the latest. That number is therefore the explicit,
tunable answer to "how soon is a new volunteer folded in": a two-to-three-week default
means a newcomer is doing real shifts within two to three weeks, without disturbing anyone
else's confirmed schedule. An organiser who wants them in *sooner* can trigger an explicit
"re-pin the window now" (re-materialise the current horizon from the fresh projection),
accepting that some already-shown confirmed assignments change; the default is not to.

### What a volunteer sees (managing expectations)

The personal page shows two clearly separated tiers so a volunteer always knows what is
expected of them:

- **Confirmed** — the commit horizon. "These turns are yours. We will remind you." Pinned,
  stable, actionable (mark done / pass / cover).
- **Outlook** — the projection beyond the horizon. "Likely yours, may still change." Shown
  greyed/labelled as tentative, not actionable, no reminders. Lets people plan ahead
  honestly without us over-promising.

### The roster tick (daily cron)

`python -m backend.cli roster-tick`, per live (non-archived) roster, does only the work
the projection cannot do lazily:

1. **Pin the incoming edge** (running rosters only; a `forming` roster is skipped entirely,
   nothing is pinned). For each occurrence now inside `[today, today + commit_horizon_days]`
   (capped by `ends_on`) that has no `Shift` row, compute its assignment from the fold
   (honouring availability, the ledger, and all materialised history up to that date) and
   insert a pinned row: `status = 'scheduled'`, or `'open'` if
   nobody is eligible. Additive and idempotent; it never touches an already-pinned row.
2. **Prune stale pins (window-only).** If a pattern edit made a pinned occurrence that is
   **not yet reminded and not yet acted on** no longer valid (date no longer occurs, slot
   dropped, before `starts_on`), delete it. Reminded or acted rows are honoured commitments
   and kept; the frozen past is never touched. Because this is bounded to the small window,
   it is cheap and its semantics are crisp (an un-acted pin is just cache).
3. **Reconcile the past.** Pinned `scheduled` rows with `on_date < today` that were never
   marked done flip to `missed`, each recording a `missed` `ShiftEvent` (drives completion
   stats and debits the ledger).

Outside the horizon there is nothing to tick: no materialisation, no reconciliation, no
divergence. The old fixed `HORIZON_DAYS = 28` constant is gone, replaced by the
per-roster, semantically-meaningful `commit_horizon_days`.

### The pure core (the functions the whole system is built from)

The scheduling system is a **pipeline of pure functions over immutable value objects**,
wrapped by one thin impure shell. The shell only (a) reads rows into value objects, (b)
writes a computed result back, (c) reads the clock, (d) sends mail. Every *decision* is
pure; the database is persistence of a result, never part of the logic. This is what lets us
test each judgement in isolation and reason locally about the system.

| Pure function | Minimal inputs | Output |
|---|---|---|
| `cycle_anchor_monday` | `starts_on` | the anchor Monday |
| `occurs_on` | `d, cycle_slots, period_weeks, starts_on` | bool |
| `occurrences_between` | chores (slots + count), `period_weeks, starts_on, ends_on`, window `[start, end]` | list of `Occurrence(chore_id, on_date, slot_index)` |
| `resolve_available` | enrolled ids, unavailability ranges, date | eligible **set** |
| `net_credit` | list of `(kind, volunteer_id)` events | `{id: int}` |
| `weight_from_ledger` | net credit | float (clamped) |
| `assign_date` | date, per-chore `(id, eligible set, count)`, rotation state `{id: V}`, weights | `{chore: assignees}` + advanced state (same-day de-collision) |
| `fold` | dated occurrences, **fixed** assignments (materialised history), eligible sets, weights | assignments for every free occurrence |
| `reconcile` | existing pins (value objects), projected assignments, `today` | `Diff{insert, prune, keep}` |
| `reminder_due` | shift (date/status/reminded/assignee-has-email), roster (days-before/enabled/hour), `now` | bool |
| `summarize_accountability` | list of `(kind, volunteer_id)` events | per-volunteer counts |

The core speaks only in small **value objects** (`Occurrence`, `PinnedShift{key, status,
reminded, acted, assignee}`, `ProjectedAssignment`, `Diff`), never ORM rows; the resolver
maps rows ↔ value objects. Three consequences worth stating, because they turn correctness
questions into testable properties:

- **`reconcile` is where edit-correctness lives.** The entire "what happens when the roster
  is edited" question reduces to: given the currently-pinned rows and the freshly-projected
  desired assignments, what do we insert / prune / keep? As a pure function its rules
  (un-acted stale pin → prune; reminded or acted → keep; `on_date < today` → never touch)
  are exhaustively testable with plain values, no DB. The tick becomes "query pins →
  `reconcile` → apply diff".
- **Shared inputs give consistency for free.** `net_credit` and `summarize_accountability`
  fold the *same* `ShiftEvent` log, so the favour ledger and the accountability display
  provably read one source. `occurrences_between` is called by *both* the tick's pin step
  and the read-side projection, so "confirmed" and "outlook" are the same oracle.
- **The removal patch is not new logic.** It is `occurrences_between` + `fold` (minus the
  leaver) + `reconcile`. That composition is *why* the short-term static patch and the
  long-term projection must agree (§7 "Removal").

So `chore_tick.run_tick` collapses to a short orchestration (read → `occurrences_between` →
resolve eligibles + weights + fixed history → `fold` → `reconcile` → apply), and every
judgement it makes is a separately-tested pure function.

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

### Pass, cover, swap, and availability

Four volunteer actions, all from the personal token page. The first three act on a
**confirmed** (pinned) occurrence; availability is the exception that reaches into the
projection.

- **Mark done.** `status = 'done'`, `done_at = now`, `completed` event. The one unambiguous
  action.
- **Pass ("I can't make it").** The pinned assignee hands one confirmed occurrence back:
  it records `deferred` and becomes `open` / "up for grabs" on every personal page and
  calendar — no automatic reassignment. Dropping a chore from the enrolment and planning
  time off over a locked-in shift hand shifts back the same way. Ledger: the passer spends
  a credit; whoever claims it earns one.
- **Cover ("I'll take yours").** A volunteer voluntarily takes another's confirmed
  occurrence. This is the answer to *"swap or extra task?"*: it is a **one-way extra task
  for the coverer plus a favour credit**, not a forced immediate swap. Rationale: a forced
  swap rigidly couples two people's calendars and needs a matching future shift to exist,
  which often it does not; the credit instead keeps each person's schedule independent and
  predictable *now*, and nets out *over time* because the coverer's credit gently biases
  the projection to hand them fewer future occurrences (and the covered volunteer more).
  Fair and predictable without calendar coupling.
- **Explicit swap (optional convenience).** Two volunteers who *want* to trade two specific
  confirmed occurrences may do so directly; both become pinned overrides and the exchange is
  ledger-neutral. Offered because sometimes people genuinely want a specific date trade, but
  it is not the primary mechanism, precisely because it is the rigid one.
- **Availability / "away" ranges.** A volunteer can mark date ranges unavailable
  arbitrarily far ahead (a holiday), which is *not* a per-shift pass because nothing is
  pinned yet. It is an input to the fold: both the projection and the pinning step exclude that
  volunteer on those dates. This lets people plan ahead without waiting for the horizon, and
  keeps the schedule honest well before anything is promised.

All of these are ordinary edit-token-authenticated `POST`/`PUT`s on the public router
(§9), and every one that changes who-does-what writes a `ShiftEvent` so the ledger and the
accountability stats stay derived from a single append-only log.

### Event log, favour ledger, and accountability

Every change of who-holds-a-shift writes one append-only `ShiftEvent`. Its `kind` records
not just the outcome but the **provenance** of the holding, because that is what both the
favour ledger and the accountability display need:

| kind | emitted when | provenance | ledger |
|---|---|---|---|
| `assigned` | the tick pins a shift to the rotation's pick (the regular case) | regular | neutral |
| `claimed` | a volunteer takes an `open` / up-for-grabs shift | pickup | + credit |
| `covered` | a volunteer takes another's confirmed shift (cover action) | pickup | + coverer, − covered |
| `inherited` | the tick force-assigns a departed volunteer's pinned shift | pickup (short-notice) | + credit (disruption) |
| `deferred` | a volunteer passes a confirmed shift | — | − credit |
| `completed` | a shift is marked done | — | — |
| `missed` | a held `scheduled` shift passes undone | — | − credit |

The **favour ledger** (fairness, above) is the net of the credit column, folded into the
rotation weight. The **accountability display** (details page, §10) reads the same log and, per
volunteer, splits their turns by provenance rather than showing one undifferentiated count:

- **Regular turns** — shifts the rotation assigned to them (`assigned`): their fair share.
- **Picked up for others** — shifts they took *beyond* their share (`claimed` + `covered` +
  `inherited`), i.e. help others did not have to do, **including slack absorbed when a
  volunteer was removed** (`inherited`).
- **Outcomes** — `completed` / `deferred` (passed) / `missed`.

Distinguishing the first two is the point: a volunteer who quietly covers for others should
read as *more* reliable, not merely "did N shifts". Both counts come straight from the
`kind` tally, so no extra column is needed beyond this vocabulary.

### Incident catalogue

Every state-changing event, and what the model does in each zone (assuming a **running**
roster; while `forming` there is no commit horizon, so every row below collapses to "the
projection reflows, nothing is promised"). The recurring theme: the **frozen past is
immutable**, the **commit horizon is a promise we keep**, and the **projection absorbs
change for free**.

| Incident | Frozen past | Commit horizon | Projection |
|---|---|---|---|
| **Organiser activates roster** (forming → running) | — | starts existing: the tick pins the first `commit_horizon_days` of occurrences | was the whole schedule; now only its far tail |
| **Volunteer enrols** | untouched | unchanged (promises stand); they appear here as the edge rolls forward, within `commit_horizon_days` | clock seeded caught-up; wins turns at their fair rate immediately, tentative sequence downstream reshuffles |
| **Volunteer leaves / unenrols** | outcome kept, assignee nulled (anonymous stats survive) | **static patch**: only the leaver's slots re-covered by the rotation (free-that-day preferred) + re-frozen (or → `open` + flagged); others' pins untouched; inheritors notified + credited | **re-derive N-1 pattern**: refolds live over the smaller pool, and eases off the slack-pickers via their credit |
| **Volunteer passes a confirmed shift** | n/a | handed off: records `deferred`, shift becomes `open` for anyone to claim; ledger: passer −1, claimer +1 | unaffected (a single-occurrence action) |
| **Volunteer covers another's shift** | n/a | coverer becomes assignee (one-way); ledger: coverer +1, covered −1 | credit gently shifts *future* marginal occurrences to rebalance |
| **Explicit two-way swap** | n/a | both occurrences re-pinned to the other person; ledger-neutral | unaffected |
| **Mark done / missed** | recorded (`done`/`missed` + event) | done set on action; missed set by tick after the date passes | n/a |
| **Availability range added** | n/a | future pins within it avoid them (re-pinned if not yet reminded) | excluded on those dates going forward |
| **Edit `starts_on`** | untouched | pins on dates that still occur keep their assignee; pins on dropped dates pruned if un-acted, honoured if reminded; new dates get pinned | reprojects instantly, no stale rows, **no divergence** |
| **Edit `period_weeks` / `cycle_slots`** | untouched | same rule: valid pins kept (same date → same assignee), orphaned un-acted pins pruned, new occurrences pinned | reprojects instantly |
| **Change `people_per_shift`** | untouched | added slots pinned + assigned; dropped-slot pins pruned if un-acted | reflects new slot count |
| **Add a chore** | n/a | its occurrences inside the window pinned at next tick | projects from `starts_on` forward |
| **Remove a chore** | events survive (`shift_id` SET NULL) | its pins CASCADE-deleted | disappears |
| **Increase `commit_horizon_days`** | untouched | more occurrences pinned at next tick | shrinks (more of it is now committed) |
| **Decrease `commit_horizon_days`** | untouched | already-pinned rows are **never** un-pinned (a promise is a promise); only future pinning slows | grows |
| **No eligible volunteers for an occurrence** | missed with no attributable assignee | pinned as `open`, organiser flagged, no reminder | shown unassigned |
| **Cron misses a day** | untouched | next run catches up (pinning idempotent); reminders send late (logged), never double | untouched (it was never materialised) |
| **Reminder send fails** | n/a | `reminder_sent_at` left null → retried next sweep | n/a |
| **Roster archived / deleted** | history retained until purge; hard-delete CASCADEs | pins CASCADE on hard-delete; email purged after grace window | gone |

Two invariants make the table safe to reason about: (1) an occurrence is pinned **at most
once** and, once pinned, only its *status/assignee* change (never its existence, except a
window-only prune of un-acted rows); (2) all "who did what" lives in the append-only
`ShiftEvent` log, so stats and the favour ledger are correct regardless of any later edit.

### Bootstrap, activation, and membership change

**Is the first-volunteer bootstrap really a different problem from adding a sixth volunteer
to a running roster?** Mechanically, no: the rotation reflows the projection and the commit
horizon folds newcomers in the same way in both cases. What differs is degree, plus one
thing in kind:

- *Degree — magnitude of reflow.* Adding the 2nd volunteer halves everyone's rate and
  reshapes most of the tentative sequence; adding the 6th shifts it modestly. Nothing
  special-cases this; it falls out of the rates.
- *In kind — there is nothing worth promising yet.* With one volunteer, a *pinned* window
  would commit that person to doing every chore alone for weeks. That is not "minimal
  disruption", it is an unreasonable promise we should never have made. The problem is not
  the reflow, it is **pinning too early**.

So bootstrap needs exactly one mechanism: **do not pin until the roster is ready.** That is
the `forming → running` gate. While `forming`, the schedule is an all-tentative draft: the
first volunteer, the second, the fifth all just reshape a projection that promises nothing,
so there is no "nonsense schedule to recreate" (that framing dissolves once nothing is
committed). The organiser presses **"Start roster"** on the details page when the base is
ready; from that instant, and only then, the tick begins pinning the commit horizon. After
activation there is no bootstrap, only the steady-state fold-in.

**Why the initial activation is a manual button, not automatic.** Only a human knows when
"enough people have signed up to begin". An automatic rule ("start at ≥ N volunteers") is a
fragile heuristic that guesses at organiser intent. A single explicit button is honest and
predictable, and it is a one-time act, so it costs the organiser almost nothing.

**Steady-state addition is automatic and needs no button.** Once running, a new enrolment:
- enters the **projection** immediately (they start winning their fair share of tentative
  future turns), and
- is folded into **pins** automatically as the horizon edge rolls forward, so they are
  doing real shifts **within `commit_horizon_days`**,
- while **disturbing no existing confirmed shift** (the fold hands the newcomer only
  occurrences not yet pinned; it never revokes a promise already made to someone else).

The new volunteer is shown as **"joining — first turns from {date}"** (that date being the
horizon edge), which is the transparent communication the "not active yet" idea was reaching
for, delivered without forcing anyone to press anything. A manual **"Fold in now /
rebalance"** button still exists on the details page, but its *only* purpose is the
impatient case: bring pending volunteers into the **current** committed window sooner than
the natural roll, which necessarily **re-pins part of that window and therefore changes
some already-shown confirmed assignments**. Because that breaks promises, it is explicit,
opt-in, and confirmation-gated ("this will reshuffle the next {n} days for {m} people").
Default behaviour never does it.

**Removal is the asymmetric case.** Addition can wait (nobody is *owed* the newcomer's
help), but removal cannot: a departing volunteer's pinned future shifts are a promise *to
the roster* that the task gets done, so they must be re-covered **immediately and
automatically**, no button. The two zones handle this with different *intents* but the
**same assignment function**, and that identity is what keeps them consistent:

- **Short term (commit horizon): freeze a minimal patch.** Pins are promises, so we only
  patch the holes: each of the leaver's pinned slots is re-covered by the rotation over
  the remaining eligible pool (preferring a volunteer free that day), and the result is
  re-pinned (frozen). **Every other volunteer's confirmed turns stay put** — a shift the
  leaver did not hold is simply never touched. This is exactly "keep it as static as
  possible and pick up the slack": patch the holes once, do not re-derive afterward. The
  inheritors are notified ("you've picked up {date}, covering for someone who left") and
  earn a small **disruption favour-credit** for the short-notice hit. If nobody is
  eligible the shift becomes `open` and is flagged to the organiser.
- **Long term (projection): re-derive the N-1 pattern.** Nothing was pinned, so the fold
  simply recomputes live over the smaller pool: the outlook becomes the genuine
  schedule-for-fewer-people, not the old pattern with gaps. Because the fold reads both
  the updated ledger and the inherited pins as history, it also **eases off the
  volunteers who absorbed the short-term slack** (their clocks ran ahead), so the far
  pattern both reflects the smaller pool and smooths the hit back out.
- The frozen **past** keeps the leaver's completed/missed outcomes anonymously for stats.

The subtlety worth stating plainly: the short-term patch and the long-term N-1 outlook
come from the *same fold*; the only operational difference is that the near term is
pinned-and-frozen while the far term is recomputed live. The clocks and the favour ledger
are what make the two intents legitimately diverge (static patch now, repaid rest later).

*Near-term sub-choice (documented):* for the leaver's *imminent* freed slots, auto-reassign
is the default (reliability first: someone is immediately on the hook and notified), with a
**pass escape hatch** so a force-drafted inheritor can immediately hand it back to `open`.
The alternative (leave `open` for claim, auto-assign only if still unclaimed near the
reminder lead time) is less disruptive to individuals but risks an uncovered gap; we prefer
guaranteed coverage plus the escape hatch.

Note the deliberate asymmetry: **joining never rewrites a promise; leaving only rewrites
the leaver's own promises.** That is the whole reliability contract in one line.

**What stays constant vs what may change (the contract to communicate):**

| | Constant / reliable | May change | Trigger | How communicated |
|---|---|---|---|---|
| **Frozen past** | never changes | — | — | historical stats |
| **Your confirmed turns** (commit horizon) | assignee changes **only** by your own action (pass/cover/swap) or if *you* leave | reassigned if you leave; re-pinned only by an explicit organiser "rebalance now" | your action; departure (auto); rebalance (manual, confirmed) | personal page "Confirmed"; notification on inherited cover |
| **The outlook** (projection) | the *pattern* (which dates recur) is stable until the organiser edits it | who is tentatively assigned reflows with every join/leave/ledger move | automatic, continuous | personal page "Outlook — tentative, may change" |
| **Roster start** | forming draft promises nothing | flips to running once | organiser "Start roster" (manual, one-time) | details page state; volunteers see "starts {date}" |

The organiser's details page therefore carries exactly two schedule controls: **"Start
roster"** (once, forming → running) and **"Rebalance now"** (occasional, opt-in, folds
pending members into the current window early at the cost of changing confirmed shifts).
Everything else is automatic and derives from the projection.

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
POST   /chores/{id}/activate                forming → running (starts pinning). One-way.
POST   /chores/{id}/rebalance               re-pin the current commit window from the fresh
                                            projection (folds pending members in early;
                                            confirmation-gated, changes confirmed shifts)
POST   /chores/{id}/archive | /restore      archive / restore
DELETE /chores/{id}                         hard-delete (archived only)
GET    /chores/{id}/volunteers              roster of volunteers + load + pending flag (NO email)
GET    /chores/{id}/schedule                confirmed (pinned) + outlook (projected) shifts
                                            + assignees + completion stats
POST   /chores/{id}/shifts/{shift_id}/reassign
                                            hand a pinned shift to a chosen enrolled
                                            volunteer (organiser "overnemen" from the
                                            calendar; records claimed/covered like the
                                            public actions)
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
POST /chores/by-token/{token}/shifts/{shift_id}/pass      ("can't make it" → reassign/open)
POST /chores/by-token/{token}/shifts/{shift_id}/cover     (take someone else's confirmed shift)
POST /chores/by-token/{token}/shifts/{shift_id}/claim     (take an `open` shift)
POST /chores/by-token/{token}/swap          {mine_shift_id, theirs_shift_id} (optional trade)
PUT  /chores/by-token/{token}/availability  {ranges[]} (away dates, feed the fold ahead of window)
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
  `LocationPicker` + the **recurrence controls** (k + derived-anchor hint +
  `commit_horizon_days`, §below) + a **Chore editor list**.
- `/chores/:id/details` → `ChoresDetailsPage.vue` via `DetailsPageShell`: overview card,
  chore list, volunteer count + per-volunteer accountability (regular turns vs picked-up
  for others vs missed, §7), the two schedule controls ("Start roster" / "Rebalance now"),
  confirmed + outlook schedule, completion rate, share link + QR via `useChoresClipboard`.
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
control for the whole roster (a stepper, k = 1..8). There is **no** anchor-Monday input:
when k > 1 the cycle anchors on the Monday of the week `starts_on` falls in (derived), so
week 1 of the grid is the week the roster begins and there is nothing extra to show or to
enter. Because k is roster-wide, changing it reshapes
every `CycleGridPicker` at once: growing k adds empty week-rows; shrinking k drops slots
whose offset is now `≥ 7k` (warn-toast naming the affected chores, then clear: no silent
data loss, no stale out-of-range slots). Add a `commit_horizon_days` control here too (the
"how far ahead is the schedule guaranteed" knob, §4/§7).

All visible strings via `t()` in `nl` + `en` (locked-step, CI fails on drift), per the UX
principles.

## 11. Cron / CLI

Two new one-shot subcommands (Coolify scheduled tasks, matching the existing cadence
style in `cli.py`):

- `roster-tick` — **daily**: pin the incoming commit-horizon edge + prune stale un-acted
  pins + reconcile past `scheduled` → `missed` (§7). No horizon-wide materialisation.
- `dispatch chore-reminder` — **hourly**: send due reminders for pinned shifts (§7).

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
- `tests/test_chore_fairness.py`: the rotation fold (pure, no RNG) — determinism (same
  inputs → same assignments) and input-order invariance; even spacing (no repeat within a
  rotation when the pool allows, bounded max gap); proportional share under weights;
  prefix consistency (fold `[a,c]` == fold `[a,b]` then `(b,c]`); fixed history advances
  clocks (a volunteer with many materialised turns is rested); same-day de-collision +
  shortfall double-booking; availability ranges exclude a volunteer on those dates.
- `tests/test_chore_recurrence.py`: the cycle-membership function — k=1 weekday match; k>1
  modulo-`7k` anchoring on the derived start-week Monday (biweekly hits alternating weeks),
  the start date landing in week 1, `cycle_slots` validated `< 7k`.
- `tests/test_chore_tick.py`: pinning is idempotent and additive; the window-only prune
  drops un-acted stale pins but keeps reminded/acted ones and never touches the past; past
  `scheduled` → `missed` reconciliation; **no pinning while a roster is `forming`**; a new
  volunteer is folded into pins within `commit_horizon_days`; a departing volunteer's
  pinned future shifts are reassigned (or go `open`) immediately.
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
3. **Scheduling model** — occurrences are a **deterministic projection** of the pattern;
   `Shift` rows are a **sparse overlay** materialised only inside a configurable
   **commit horizon** (`commit_horizon_days`) or on action (§7). The past is frozen, the
   horizon is a kept promise, the projection absorbs edits and membership change for free.
   Kills the edit-divergence bug at the root and gives unbounded, honest lookahead.
4. **Fairness** — a **virtual-time fair rotation** (stride scheduling, §7): a pure
   date-ordered fold over occurrences + materialised history, picking the lowest-clock
   eligible volunteer and advancing their clock by `1/weight`. Evenly spaced turns and
   exactly proportional shares by construction, tilted by a favour ledger derived from
   `ShiftEvent`; same-day de-collision built in. Pure over its inputs, no RNG,
   projectable, prefix-consistent with pinning. Replaces two earlier rules: the original
   greedy-random one (non-deterministic, unprojectable) and the per-date weighted
   rendezvous hash (clumped turns, non-proportional weights).
5. **Takeover** — modelled as a one-way **cover** (extra task + favour credit that
   rebalances the future), not a forced immediate swap; an explicit two-way swap is offered
   as an optional convenience (§7).
6. **New-volunteer fold-in** — bounded by `commit_horizon_days`: a newcomer is doing real
   pinned shifts within that window, without disturbing anyone's confirmed schedule.
7. **Multi-person chores** — `people_per_shift` ships defaulting to 1 (one Shift row per
   occurrence), with the schema and assignment designed for N from day one.
