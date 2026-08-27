# Design: recurring events

Status: implemented. This is a full rewrite. The recurrence rule is now the
chores roster's k-week cycle model, reused wholesale: the same
``period_weeks`` cycle length, the same ``starts_on`` anchor, the same
``cycle_slots`` weekday grid, and the same pure date math in
``backend/services/recurrence.py``. An event is a single recurring thing
(one definition), so it carries the rule that a roster splits across
roster + chore. The earlier event design invented its own
``cadence_weeks`` + ``occurrence_count`` scheme; that was the mistake this
rewrite deletes. There is no backwards compatibility to keep (pre-launch,
rule #1): the old columns and the old edit UI are replaced, not adapted.

The rest of the model (occurrences with their own public pages,
registrations as order headers, line-item signups, per-occurrence mail,
the privacy invariants) is unchanged and still correct. What changes is
only how the recurrence rule is stored, how dates are enumerated, and the
edit page. Those three are brought onto the roster's rails.

## The one structural decision (unchanged)

A recurring event is **one database row**: the definition. It holds the
shared content (name, description, location, the sign-up questions, the
toggles, the locale, the image) and the recurrence rule. It is the single
source of truth and the only thing an organiser ever edits.

Its **occurrences are materialised over time**, not up front. A daily tick
creates the concrete, dated occurrences that fall inside a rolling
horizon; everything past the horizon is a projection, not a row. Each
materialised occurrence is a real, dated instance with **its own public
sign-up page**, its own sign-ups, and its own reminder/feedback mail,
exactly like a standalone event.

Three things follow:

1. **The parent is the only editable entity.** An occurrence has no
   content of its own (its content is the parent's), so "edit one
   occurrence" is not a defined operation. To change the course you edit
   the one row. To end it early or drop the tail you shorten its span.
   That is a rule edit, not an occurrence edit.
2. **Occurrences are materialised over time.** The row stores the rule;
   the tick turns the next slice of it into real occurrences as the
   calendar advances. This is the roster engine, and it is now shared with
   it in code, not just in spirit.
3. **Each occurrence has its own public page, and each page can sign a
   visitor up for several occurrences at once.** The public surface is the
   per-occurrence sign-up pages plus the chapter agenda, not a single
   parent page. The sign-up form on any occurrence page carries a
   checklist of the upcoming occurrences, so a visitor who can't make this
   one can book the next two, or the whole course, in one submission.

## The recurrence rule is the roster's k-week cycle

An organiser doesn't think "every 2 weeks for 6 sessions". They think
"Tuesdays and Thursdays, for the next 6 weeks", or "alternating Tuesdays
and Thursdays". That is a weekday pattern over a repeating cycle of weeks,
which is exactly what the chores roster already models. We reuse it.

The rule has four parts, all lifted from the roster:

- **``period_weeks``** (the cycle length k, 1 to 8). k=1 is a plain weekly
  pattern. k=2 is a two-week cycle, so the grid can say "week A: Tuesday,
  week B: Thursday". Set once for the event.
- **``starts_on``** (a ``date``): the anchor and the earliest date an
  occurrence may fall on. Cycle week 0 runs from the Monday of the week
  ``starts_on`` falls in, derived by ``recurrence.cycle_anchor_monday`` and
  never stored, identical to the roster. The start date is therefore always
  in week 0: "every other Thursday, starting Thursday" means that Thursday
  and the one a fortnight later.
- **``cycle_slots``** (``list[int]``): the selected weekday cells, each a
  flat offset ``week_index * 7 + weekday`` (Mon=0), range
  ``0 .. 7*period_weeks - 1``. This is the exact ``cycle_slots`` shape the
  roster's ``CycleGridPicker`` already produces. Alternating Tue (week 0)
  and Thu (week 1) on a 2-week cycle is ``[1, 10]``.
- **The span**: ``span_weeks`` (an ``int``, the scroller) or ``null`` (the
  infinite toggle: open-ended, rolling). A finite span runs the pattern
  for that many weeks from ``starts_on``.

"Does this event fall on date d" is answered by the roster's pure
function, reused verbatim:

```python
recurrence.occurs_on(d, cycle_slots=event.cycle_slots,
                     period_weeks=event.period_weeks, starts_on=event.starts_on)
```

Events add exactly one thing over the roster: a **time of day**. Roster
shifts are all-day; an event happens at a wall-clock time. So the event
also stores ``start_time`` and ``end_time`` (naive Europe/Amsterdam
wall-clock ``time`` values), applied to every occurrence's date. An
occurrence's concrete ``starts_at`` is ``on_date`` + ``start_time``.

**A one-off is ``cycle_slots == []``.** With no weekday selected there is
no pattern, so the event is a single occurrence on ``starts_on`` at
``start_time``. This is the one documented branch in the enumerator (empty
slots means "one occurrence at the anchor" for events, where for the
roster it means "never"); it is not a flag and not a hack. The "repeat"
toggle in the UI is just "is ``cycle_slots`` non-empty", derived, never
stored as its own column (rule #1).

## Data model

The occurrence / registration / signup / dispatch spine is unchanged. Only
the ``events`` schedule columns change: the old
``first_starts_at`` / ``first_ends_at`` / ``cadence_weeks`` /
``occurrence_count`` are replaced by the roster rule + a time of day.

```
events            (the definition, one row per event, recurring or one-off)
  OrgEntity spine: chapter_id, created_by, archived_at, locale, image,
    name, image_artist_instagram
  content:  topic, location, latitude, longitude,
            source_options, help_options,
            feedback_enabled, reminder_enabled, listed
  schedule: starts_on            DATE      # anchor + earliest date (roster starts_on)
            start_time, end_time TIME      # shared wall-clock time of day
            period_weeks         INT (1..8, default 1)   # the k-week cycle
            cycle_slots          JSON list[int]          # weekday grid offsets; [] = one-off
            span_weeks           INT NULL   # span in weeks; NULL = open-ended (infinite)
            horizon_days         INT default 90          # how far ahead to materialise
  # No concrete date/time on the event: a concrete instance is an occurrence.

occurrences       (dated instances of an event; materialised over time)
  event_id          FK -> events (NOT NULL, ON DELETE CASCADE)
  starts_at, ends_at   concrete naive wall-clock = on_date + event start/end time
  slug              its own public URL (/e/{slug}), unique
  UNIQUE (event_id, starts_at)
  # No content of its own; all content is read through the event_id join.
  # "sessie i van N" is NOT stored: it is the occurrence's date rank,
  # derived at read time (session_index / total_sessions), so a rule edit
  # that changes which dates recur can't leave a stale ordinal behind.

registrations     (one person's booking, the order header)
  event_id        FK -> events (NOT NULL, ON DELETE CASCADE)
  edit_token_hash, link_recovered_at   # the one magic link that manages the booking
  display_name    optional pseudonym
  party_size      how many people this person brings
  # no email, no occurrence: a header over its line items.

signups           (the line items, one per occurrence the person signed up for)
  registration_id FK -> registrations (NOT NULL, ON DELETE CASCADE)
  occurrence_id   FK -> occurrences   (NOT NULL, ON DELETE CASCADE)
  source_choice, help_choices          # "how did you hear", "I can help with"
  UNIQUE (registration_id, occurrence_id)

email_dispatches  FK -> occurrences (occurrence_id)   # per-occurrence reminder/feedback ciphertext
```

Why this is the normalised design, not a shortcut:

1. **The rule matches how organisers think and is shared with the
   roster.** ``period_weeks`` + ``cycle_slots`` + ``starts_on`` is the
   roster's exact representation, so the same pure ``recurrence.occurs_on``
   answers "which dates" for both. No parallel cadence math.
2. **A booking is an order with line items.** One ``registration`` (edit
   link, pseudonym, party size) with one ``signup`` per occurrence picked.
   Signing up for the whole course is the same registration with several
   line items; the multi-occurrence sign-up is native to the model.
3. **No duplicated content.** An occurrence carries only its ordinal, its
   concrete datetimes, its slug, and its line items. Everything else reads
   through ``event_id``. Editing the event updates every occurrence at
   once, because nothing is copied to go stale.
4. **The public slug is on the occurrence.** The ``events`` row has no
   public sign-up page of its own; the email graph stays keyed on the
   occurrence and carries no link back to a registration or line item, so
   "feedback carries no sign-up link" holds per occurrence.

## Materialisation: finite events in full, open-ended by horizon

The materialisation depth depends on whether the span is finite. This is a
deliberate rule, to kill the confusing case where the page says "6 sessies"
but a visitor can only find 4 (because the last two sit beyond a horizon):

- **A finite event materialises every session up front.** A one-off
  (``cycle_slots == []``) and any event with a set ``span_weeks`` have a
  known, bounded session list, so **all** of their occurrences are created
  at event-creation time, ignoring ``horizon_days`` entirely. "6 sessies"
  always means six real, findable, sign-up-able occurrence rows from the
  moment the event is saved. There is nothing for the tick to add later, and
  nothing is ever shown as a beyond-horizon projection.
- **An open-ended event (``span_weeks == null``) materialises by horizon.**
  An unbounded weekly meetup can't be fully materialised, so it creates only
  the occurrences inside ``today + horizon_days`` (default 90). The rest are
  a projection: shown as "upcoming dates" for context, not yet sign-up-able.
  A nightly tick pulls the next dates across the horizon into real rows as
  the calendar advances. ``horizon_days`` is therefore only meaningful for
  open-ended events.

The date math is the shared pure ``recurrence.occurs_on`` /
``recurrence.cycle_anchor_monday`` in
``backend/services/event_recurrence.py`` (no bespoke week-shift). Enumerate
the pattern's dates from ``starts_on`` forward; for a finite event take them
all, for an open-ended one stop at the horizon. Insert an ``Occurrence``
(keyed on its date) for each **future** date that doesn't exist yet. The
"sessie i van N" ordinal is the occurrence's rank among the event's rows,
derived at read time (``session_index`` / ``total_sessions``) and never
stored, so a rule edit that strands a frozen past session still leaves every
session with a number of its own.

**A recurring pattern's history is immutable: it only ever materialises
future occurrences.** A past occurrence of a recurring event exists on disk
for exactly one reason: it was materialised while still in the future and
time then passed it. A pattern never fabricates a row for a date already in
the past and never rewrites one. So "materialise all sessions of a finite
course" means all of its **future** sessions (for the normal case of a start
today or later, all of them); a course whose start is already behind ``now``
gets only its remaining future sessions, not a back-filled history that never
happened. This keeps the past showing what actually occurred while the future
follows the current plan, and it holds on every read surface for free because
they all just read occurrence rows.

**A one-off is the deliberate exception**, because its single session *is*
the event, not a member of a pattern. The organiser sets that one date
freely, and may put or correct it in the **past** (recording an event that
already happened, or fixing a wrong date). So a one-off's single occurrence
is created and re-pointed to exactly the date the organiser picks, past or
future, carrying its sign-ups and dispatches; there is no pattern history to
protect and no migration ambiguity. (The demo seed leans on the same
mechanism to give the straddling demo course believable past sessions on
first boot.)

The one-shot cron ``python -m backend.cli event-tick`` runs nightly and
sweeps only what open-ended events need. A finite event's occurrences all
exist from creation, so the tick is a no-op for it.

**This is the only place materialisation lives.** Materialisation writes
occurrence rows; every read surface is then a plain "select the event's
occurrences" query and inherits the depth rule for free, with no per-surface
horizon logic:

- the **chapter agenda** (``services/agenda.py``) reads occurrence rows in
  its rolling display window;
- the **public occurrence pages** read the event's future occurrences for
  the calendar picker;
- the **organiser detail page** reads the event's occurrences for the
  calendar day switcher.

So a finite "6 sessies" course shows all six on all three surfaces the
moment it is saved, because all six are rows, not because any surface
special-cases finiteness. The single exception is the open-ended public
page, which additionally renders the beyond-horizon dates as read-only
"not-yet-open" context (a projection, never rows); a finite event has no
projection anywhere, because it has no beyond-horizon dates.

## Editing (the parent, and only the parent)

There is exactly one edit surface: the recurring event's own edit page.

- **Content edits** (name, description, location, questions, toggles,
  locale, image) take effect everywhere at once, because occurrences read
  content through the parent. No propagation.
- **Rule edits** (``period_weeks``, ``cycle_slots``, ``starts_on``,
  ``start_time`` / ``end_time``, ``span_weeks``, ``horizon_days``)
  re-materialise to the same depth rule as creation (a still-finite event
  ends up with **all** its new sessions as rows, an open-ended one with the
  in-horizon slice) and **reconcile the existing future occurrences and
  their sign-ups onto the new schedule** (the algorithm below). Past
  occurrences are frozen. Setting a finite ``span_weeks`` materialises the
  full course at once; clearing it hands the tail back to the nightly tick.
- **Ending a course early or dropping the tail** is shortening
  ``span_weeks`` (or clearing it toggles back to open-ended). **Cancelling
  a single session is not a feature**; an occurrence is not independently
  editable.

### Reconciling sign-ups when the schedule changes

An occurrence carries sign-ups (line items) and per-occurrence
reminder/feedback dispatches. When a rule edit changes which dates the
pattern produces, the earlier design **kept any booked occurrence whose date
fell off the pattern**. That is the worst option: it leaves a "session" alive
on a date the schedule no longer contains, so the event advertises a class
that doesn't exist. The reconciliation below never lets an occurrence survive
off-pattern; instead it moves sign-ups to a real new session where that is
meaningful and drops them where it is not.

**A one-off is reconciled trivially and can move into the past.** With
``cycle_slots == []`` there is exactly one occurrence, the event itself, so
an edit just re-points that single row to ``starts_on`` + the times, wherever
the organiser puts it (past or future), and its sign-ups and dispatches ride
along on the row. There is no pattern history to protect. Everything below is
about **recurring** events.

**For a recurring event, only the future is reconciled. The past is frozen,
entirely.** A rule edit never creates, re-times, deletes, or re-homes any
occurrence with ``starts_at <= now``, and it never migrates a past session's
sign-ups. Past attendance is history and stays exactly as it happened.
Everything below concerns future occurrences only.

Classify each **future** occurrence row by the edited rule (membership tested
with ``occurs_on`` within the span, so it tracks the **pattern**, not the
materialisation horizon):

1. **Uniform shift.** If the whole future schedule just translated by a
   single constant Δ (the new future pattern equals the old future dates plus
   one common offset), re-point each future occurrence's date by Δ. Sign-ups
   and dispatches ride along on the row, so every attendee stays matched to
   their moved session and nothing is lost. This is the "wrong start date /
   wrong weekday" fix. A session a negative Δ would push to ``<= now`` can't
   occur in a time already gone, so it is dropped (its sign-ups lost). Then
   materialise any extra dates a grown finite span adds.

2. **Structural change** (an add/remove that is not a uniform shift):
   - **Surviving** (date still produced): kept, times re-pointed.
   - **Added** (future pattern date within the materialisation depth, no row
     yet): materialised as an empty occurrence.
   - **Removed** (future occurrence the rule no longer produces): migrate its
     sign-ups to a replacement, or lose them. Let ``L`` / ``R`` be the nearest
     **surviving** future occurrences before / after the removed date; the
     candidates are the **added** dates strictly inside the gap ``(L, R)`` (a
     new session *between the removed one and an untouched one*, looking both
     ways). Move the sign-ups to the **closest** candidate (ties toward the
     earlier date); if there is none, the sign-ups are **lost** and the row
     deleted. A registration landing twice on one target (two of its removed
     sessions collapsing onto one new session) keeps a single line item. When
     there are no surviving future sessions at all (a full replacement), every
     gap is unbounded, so each removed session migrates to its closest new
     one rather than being lost.

The complete edit space, its future effect, and the intuitive outcome:

| Rule edit | Future effect | Sign-ups |
|---|---|---|
| One-off date corrected (incl. into the past) | the single session re-points to the new date | sign-ups + dispatches ride the row; nothing lost |
| ``start_time`` / ``end_time`` only | dates unchanged | all kept, times re-pointed; nothing lost |
| Start date slid, finite | whole schedule translates by Δ | uniform shift: every future session + its sign-ups move by Δ (any pushed into the past are dropped) |
| Start moved later, open-ended | leading future sessions drop | those sign-ups lost (removal, no in-gap replacement) |
| Start moved earlier, open-ended | leading sessions added | new empty sessions; existing kept |
| Span shortened, finite | tail sessions drop | tail sign-ups lost |
| Span lengthened, or made open-ended | tail sessions added | new empty sessions; existing kept |
| Made finite from open-ended | sessions past the span drop | those sign-ups lost |
| Weekday added to the grid | sessions added | new empty; existing kept |
| Weekday removed from the grid | those sessions drop | their sign-ups lost (no in-gap replacement) |
| Every weekday moved uniformly (all Tue to Wed) | translation by the day offset | uniform shift: sign-ups follow |
| One of several weekdays moved (Tue+Thu to Wed+Thu) | Tue removed, Wed added between surviving Thu | Tue sign-ups migrate to the new Wed |
| Cadence lengthened (weekly to bi-weekly) | alternate sessions drop | dropped-session sign-ups lost (kept sessions already exist, nothing new in the gap) |
| Cadence shortened (bi-weekly to weekly) | in-between sessions added | new empty; existing kept |
| Recurring to one-off | collapses to the single date | the occurrence at that date survives (else the earliest is re-pointed onto it); the other sessions' sign-ups are lost |
| One-off to recurring | the single session vs the new series | survives if its date is in the series, else migrates to the nearest new session; other series dates added empty |
| Total weekday/cadence swap, no overlap | all old drop, all new added | each old session's sign-ups migrate to their closest new session |
| Horizon shrunk (open-ended, advanced) | fewer future rows materialised; pattern unchanged | booked occurrences past the new horizon still match the pattern, so they survive; nothing lost |
| Archive / restore | not a rule edit | no reconciliation |

**Dispatches follow the occurrence, by date.** A reminder/feedback dispatch
keys on the occurrence (a date), never on a sign-up, so it moves with the
session:

- A **shifted** occurrence keeps its dispatch rows (they reference the same
  row); the reminder/feedback window recomputes from the new date.
- A **removed** occurrence whose sign-ups migrate hands its **pending**
  dispatches to the target occurrence, so attendees are reminded about where
  they now attend. (Addresses are encrypted with a random nonce and carry no
  sign-up link, so duplicate dispatches on the target can't be de-duplicated;
  a person on both sessions may get two reminders, a tolerated edge.)
- A **dropped** occurrence's dispatches are deleted with it (cascade), so no
  mail goes out for a session that no longer exists.
- A reminder already **sent** can't be recalled, so shifting a session inside
  its 72-hour reminder window may leave some attendees reminded of the old
  date. Only pending dispatches re-aim cleanly.
- **Past** dispatches, like everything past, are untouched.

## Frontend: the edit / creation page

The recurrence editor on the event form reuses the roster's controls
directly. Nothing new is built where a roster component already exists.

The controls, in order:

1. **A "repeat" toggle.** Off is a one-off: only the single date + time
   pickers show, and ``cycle_slots`` is ``[]``. On reveals the recurrence
   controls below.
2. **A cycle-length scroller** ("herhaalt elke [k] weken"): a
   ``NumberStepper`` (min 1, max 8) bound to ``period_weeks``. This is the
   "number of weeks pattern" control. Reused, not rebuilt.
3. **A week-based day grid**, ``period_weeks`` rows tall, seven weekday
   columns (Mon..Sun): the ``CycleGridPicker`` component, ``v-model`` bound
   to ``cycle_slots``, driven by ``:period-weeks``. Toggling a cell adds or
   removes its ``week*7 + weekday`` offset. This is how "alternating
   Tuesdays and Thursdays" is expressed. Reused verbatim.
4. **A span scroller** ("gedurende [n] weken"): a second ``NumberStepper``
   bound to ``span_weeks``. This replaces the old session-count control:
   the organiser picks a number of **weeks**, not sessions.
5. **An "infinite / doorlopend" toggle** directly after the span scroller.
   On clears ``span_weeks`` to ``null`` (open-ended) and disables the span
   scroller; off restores a finite span.

Lowering ``period_weeks`` prunes now-out-of-range ``cycle_slots`` via the
same ``watch`` the roster page uses (drop every offset ``>= 7*k``), so the
payload never carries a slot the shorter cycle can't hold. The old
``repeatMode`` / ``spanMode`` / custom-cadence controls are deleted.

The read-only twin, ``WeekdayGrid`` (labels injected, no i18n/PrimeVue
dependency), renders the chosen pattern on the organiser detail page and
on the public occurrence page, so a visitor sees "this runs Tue + Thu"
without a bespoke component.

## Public pages (each occurrence its own, multi-occurrence sign-up on each)

Each materialised occurrence has its own ``/e/{occurrence-slug}`` page
rendering the event's content (through the parent) and this occurrence's
date. Submitting the sign-up form creates **one registration** with **one
line item per selected occurrence**, plus a per-occurrence reminder/feedback
dispatch for each.

**The date picker on a recurring event is a calendar.** A one-off page
shows only its single date. A recurring event's page shows a calendar of
its dates (the shared ``MonthGrid`` component, reused not rebuilt), so a
visitor sees the shape of the course and picks the sessions they want. Each
**available date** (a materialised occurrence with ``starts_at`` in the
future) is a selectable, toggleable button cell via ``MonthGrid``'s
``clickable(iso)`` + ``day-click``; past dates and (for open-ended events)
beyond-horizon dates render as non-clickable context.

**A "select all" toggle flips the calendar between opt-in and opt-out,**
because the right default differs per visitor:

- **Toggle off (opt-in, the default): the visitor picks the sessions they
  want.** Only the landing date starts selected; tapping a day adds it.
  Copy makes clear this is a hand-picked set, so for an open-ended course
  they will have to come back and select **new** sessions themselves as
  those are scheduled (the booking never auto-grows).
- **Toggle on (opt-out): the visitor is signed up for every upcoming
  session and deselects the ones they can't make.** Flipping it on selects
  every available date; individual days stay **toggleable** so the visitor
  can uncheck the odd session they'll miss (it is not a locked "all or
  nothing"). Copy reminds them that, for an open-ended course, later
  sessions keep appearing, so they may have to come back and **deselect**
  ones they don't want.

For a finite event this distinction is complete and honest, because every
session is materialised (see the materialisation rule): "select all" really
does cover the whole course, with nothing hidden beyond a horizon. For an
open-ended event, "all" means every session that exists now; the reminders
above set the expectation that the set isn't the infinite future.

Submitting sends the explicit selected occurrence ids. The one exception is
opt-out with nothing deselected, which sends the ``all_upcoming`` flag so
the **server** resolves "every future occurrence", so a stale page can't
miss a just-materialised session or book one already past. Either way the
server validates every target is a future, materialised occurrence of this
event.

The submission creates one registration with one line item per selected
occurrence; the booking is a snapshot, it never auto-grows as new sessions
materialise. Only materialised occurrences are selectable; for an open-ended
event the beyond-horizon dates are shown as not-yet-open context.

### Managing a booking: the secret link is the sign-up page in "manage" mode

The edit link (``?s={token}``) must open **the same calendar and toggle as
sign-up**, pre-filled with the attendee's current sessions, not a separate
cancel-only list. The old edit surface (a flat list of the booked
occurrences, each with a withdraw button, no calendar, no toggle) is wrong:
it doesn't match the sign-up page and only lets the attendee cancel, never
add. The rework:

- **Same ``MonthGrid`` calendar + select-all toggle as sign-up**, seeded
  with the attendee's booked sessions selected. It is the sign-up component
  in "manage" mode, not a bespoke screen.
- **The attendee modifies the booking, not just cancels it.** They can add
  future sessions they weren't on and deselect future ones they can't make;
  name and party size stay editable; a "withdraw entirely" action removes
  the whole booking. Saving **diffs** the chosen future set against the
  booking's current future line items: create a line item (and its
  per-occurrence reminder/feedback dispatch) for each newly-selected
  occurrence, delete the line item for each deselected one, leave everything
  else alone.
- **Past occurrences are frozen.** A session that has already started or
  ended is shown in the calendar as read-only history (marked attended /
  past), never selectable or deselectable. You cannot add yourself to a
  session that already happened, and you cannot withdraw from one after it
  occurred, because attendance for a past date is settled. Only future
  occurrences are editable, on both the sign-up and the manage surface.

Backend impact:

- Extend ``BookingOut`` to carry what the calendar needs, mirroring
  ``PublicEventOut``: ``is_recurring``, ``total_sessions``, the event's
  future materialised occurrences (the addable set), the attendee's
  currently-booked occurrence ids (the pre-selection), and the attendee's
  **past** occurrences (rendered locked).
- Add ``PUT /api/v1/events/by-token/{token}/occurrences`` taking
  ``{occurrence_ids, all_upcoming}`` (the same shape sign-up posts). The
  server diffs against the booking's **future** line items only: it inserts
  line items + dispatches for newly-selected occurrences, deletes them for
  deselected ones, refuses to touch any line item whose occurrence is
  already past, and validates every target is a future materialised
  occurrence of this event. ``all_upcoming`` resolves server-side exactly
  as on sign-up.
- Guard the existing per-occurrence ``withdraw`` so it rejects a past
  occurrence (409), keeping "you can't undo attendance history" a single
  rule, not a frontend-only nicety.

Database impact: **no schema change.** Managing a booking is add/remove of
``signups`` line items and their ``email_dispatches``, on the existing
tables; a booked past session is simply an older line item that stays put.

Frontend impact: ``PublicEvent.vue`` edit mode reuses the sign-up calendar +
toggle (same components, same opt-in/opt-out semantics) instead of the
withdraw list, with past cells rendered locked, and saves via the new
set-occurrences endpoint.

Seed impact: the demo course is moved to **straddle "now"** (some sessions
already past, some still upcoming) and its multi-occurrence booking spans
both, so the manage page demonstrates locked-past sessions alongside
editable-future ones out of the box.

## Chapter agenda

Unchanged. The agenda lists materialised upcoming occurrences within a
fixed one-month display horizon (``services/agenda.py``), each as its own
card linking to its occurrence page, carrying the "sessie i van N" badge.
The display horizon is separate from, and shorter than, the materialisation
horizon.

## Mail, stats, privacy

Unchanged. Each occurrence behaves like a standalone event for mail: its
line items drive its own reminder (before its date) and feedback (after its
date), keyed on the occurrence. Every privacy invariant holds per
occurrence: encrypted email only on the dispatch rows, the wipe rule per
occurrence, the open-source disclosure on every sign-up page, no new PII
surface. The ``registrations`` grouping row holds only a pseudonym, party
size, and the edit-link hash, never an email; the email graph keys on the
occurrence and never links back to the registration or its line items.

## Organiser surface

- **Dashboard**: one row per event (not per occurrence), linking to its
  detail/edit page, with a one-line recurrence summary (e.g. "Wekelijks ·
  Di + Do · 6 weken" or "Tweewekelijks · doorlopend").
- **Detail / edit page**: edit the parent's content and rule. The only
  actions are on the event itself (edit, shorten/extend the span, archive);
  no occurrence has an edit or cancel control.

### The "Aanmeldingen" section (calendar + one day at a time)

The signups section keeps its name, **"Aanmeldingen"** (the earlier rework
wrongly renamed it to a "Sessies" heading; restore the original i18n key).
The foldable per-occurrence panels (``OccurrenceSignupPanel``) are deleted.
Instead the section shows **one day at a time**, in the exact same signups +
stats layout the other three entity types (forms, datepolls, chores)
already use:

- **At the top of the section, a calendar** (the shared ``MonthGrid``) whose
  occurrence days are clickable. Selecting a day is switching which
  occurrence's signups are shown; the current day is highlighted, and the
  calendar navigates months. A one-off event has a single day, so the
  calendar collapses to just that date (or is omitted).
- **Below the calendar, the selected day's signups and stats**, rendered in
  the shared format: the ``StatBar`` counts and the by-help / by-source
  breakdowns for that occurrence, then the signups table (display name,
  party size, source, help, the ``RecoverLinksPill`` edit-link recovery,
  per-row delete) and CSV export, exactly as ``FormDetailsPage`` /
  ``DatepollDetailsPage`` / ``ChoresDetailsPage`` present a submission list.
  Nothing foldable, nothing bespoke.

This means the signups and stats queries are scoped to the selected
occurrence: ``useEventSignups`` / ``useEventStats`` take an
``occurrence_id`` and hit the existing per-occurrence endpoints
(``/api/v1/events/{id}/occurrences/{occ}/signups`` and the per-occurrence
stats), so switching days just re-scopes the same shared components. The
feedback summary below stays as it is.

## What is reused (the reuse mandate, explicit)

Backend:

- ``backend/services/recurrence.py`` (``occurs_on`` and
  ``cycle_anchor_monday``), the pure date math, shared with the roster.
  ``event_recurrence.py`` calls these; it does not re-derive cadence.
- The ``cycle_slots`` flat-offset representation and its normalise /
  dedupe / range-check validation (reject on create, clamp on update),
  mirroring ``RosterCreate`` / ``RosterUpdate``.
- The horizon-cap pattern from ``chore_tick.horizon_end``, but only for
  **open-ended** events; a finite event ignores the horizon and materialises
  its whole span.

Frontend:

- ``NumberStepper.vue`` for the cycle-length scroller and the span scroller.
- ``CycleGridPicker.vue``, the interactive week x weekday grid,
  ``v-model`` = ``cycle_slots``.
- ``WeekdayGrid.vue``, the read-only pattern display on the detail and
  public pages.
- ``MonthGrid.vue``, the shared monthly-calendar shell for the public
  recurring-event date picker (selectable date cells + select-all).
- The shrink-clamp ``watch`` on ``period_weeks`` from ``ChoresEditPage``.

## Downstream changes to make

1. **Model** (``backend/models/events.py``): replace the four old schedule
   columns with ``starts_on`` (Date), ``start_time`` / ``end_time`` (Time),
   ``period_weeks`` (Int), ``cycle_slots`` (JSON), ``span_weeks`` (Int
   null), ``horizon_days`` (Int).
2. **Schema** (``backend/schemas/events.py``): ``EventCreate`` /
   ``EventUpdate`` take the new fields; add the ``cycle_slots`` validator
   (sorted, deduped, ``< 7*period_weeks``; reject on create, clamp on
   update) and ``span_weeks >= 1 or null``.
3. **Recurrence service** (``backend/services/event_recurrence.py``):
   enumerate via ``occurs_on`` (occurrences keyed on their date), derive the
   session ordinal at read time (``session_index`` / ``total_sessions``),
   and handle the ``cycle_slots == []`` one-off case. **Materialisation
   depth is finite-aware:** a finite event (one-off, or ``span_weeks`` set)
   materialises **every future** session ignoring ``horizon_days``; an
   open-ended event (``span_weeks == null``) materialises only the in-horizon
   slice and the nightly tick extends it, with the beyond-horizon dates
   exposed as ``projected_future_specs`` for the public page only.
   **Materialise never creates a past-dated occurrence** (history is
   immutable; past rows exist only by time passing). ``reconcile`` touches
   only future occurrences, freezing the past entirely, and migrates
   sign-ups + their pending dispatches onto the new schedule per the case
   table (uniform-shift re-point; otherwise surviving / added / removed with
   nearest-in-gap migration or loss), so no occurrence ever survives
   off-pattern.
4. **Frontend edit page** (``EventFormPage.vue``): swap the old
   repeat/span controls for the reused ``NumberStepper`` +
   ``CycleGridPicker`` + toggles described above.
5. **Frontend summary + display** (``lib/recurrence.ts``, detail + public
   pages): summarise ``period_weeks`` + ``cycle_slots`` + span; render the
   pattern with ``WeekdayGrid``.
6. **Public date picker** (``PublicEvent.vue``): on a recurring event, a
   ``MonthGrid`` calendar of selectable date cells with a "select all"
   **toggle** (a real switch, not a checkbox) that flips opt-in vs opt-out:
   off pre-selects only the landing date and the visitor adds days; on
   pre-selects every available date and the visitor deselects days
   (individual cells stay toggleable, never locked). Each mode shows its own
   reminder about hand-picking / deselecting future sessions. Submit sends
   explicit occurrence ids, except opt-out-with-nothing-deselected which
   sends ``all_upcoming`` for server-side resolution. A one-off keeps its
   single-date page.
7. **Detail page "Aanmeldingen" section** (``EventDetailsPage.vue``): delete
   the foldable ``OccurrenceSignupPanel``; restore the "Aanmeldingen"
   heading; add a ``MonthGrid`` day switcher at the top and render the
   selected day's signups + stats in the shared ``StatBar`` + signups-table
   format the other three entities use. Scope ``useEventSignups`` /
   ``useEventStats`` by ``occurrence_id``.
8. **Booking-edit (manage) page** (``PublicEvent.vue`` edit mode +
   ``routers/signups.py`` + ``BookingOut``): replace the cancel-only
   occurrence list with the sign-up calendar + toggle, pre-filled with the
   booking's future sessions and showing past sessions locked. Extend
   ``BookingOut`` with the calendar data (``is_recurring``,
   ``total_sessions``, the event's future occurrences, the booked ids, the
   past occurrences). Add ``PUT /by-token/{token}/occurrences`` that diffs
   the chosen future set against the booking's future line items
   (add/remove line items + dispatches, never touch past ones), and guard
   per-occurrence ``withdraw`` to 409 on a past occurrence.
9. **Seed** (``backend/seed.py``): the demo course straddles "now" with a
   booking on both a past and a future session (manage-page showcase). Since
   materialise no longer fabricates past occurrences, the seed **inserts the
   course's past occurrences directly** to simulate a running course.
10. **Migration**: one Alembic revision moving the schedule columns,
   data-preserving. Existing events become one-offs: ``starts_on`` and
   ``start_time`` / ``end_time`` from the old datetimes, ``cycle_slots =
   []``, ``span_weeks = null``, ``period_weeks = 1``. Existing signups
   become one registration + one line item each on the event's single
   occurrence (as in the prior migration). Columns are added nullable,
   backfilled, then set NOT NULL before the old columns are dropped, so no
   live data is lost.
11. **Regenerate** ``openapi.json`` + ``frontend/src/api/schema.ts``.

### Database impact of the finite-vs-horizon rule

No schema change: ``occurrences`` and the recurrence columns are unchanged.
The only effect is **row count and when rows appear**. A finite event now
holds one ``occurrences`` row per session from creation (a 6-session course
is 6 rows immediately; a 20-week weekly course is 20 rows, not the ~13 that
fit a 90-day horizon). An open-ended event still holds at most the
in-horizon slice, growing by the nightly tick. Volumes stay small (courses
are dozens of rows, not thousands), and because every read surface is a
straight occurrences query, this is the single lever that makes "6 sessies"
resolve to six findable pages everywhere. Existing events, migrated as
one-offs, are one row each and unaffected.
