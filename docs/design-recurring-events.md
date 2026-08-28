# Recurring events

An event is a definition plus a recurrence rule. The dates it produces
are `Occurrence` rows, and everything public points at one of those.

## The rule

The same k-week cycle the chore rosters use, from
`services/recurrence.py`: a period of `k` weeks and a set of slots
inside it, where a slot is `week * 7 + weekday`. A one-off event is the
degenerate case with no slots.

`span_weeks` bounds a finite series ("eight weeks of this"). Without it
the series is open-ended.

## Materialisation

A finite series is materialised in full at save time. An open-ended one
is materialised to a rolling horizon (`horizon_days`, default 90) and
extended by `python -m backend.cli event-tick`.

Occurrences are rows because they carry state: their own public slug,
their own sign-ups, their own dispatch rows. A date computed on the fly
could not hold any of that.

## Editing

The parent is the only thing an organiser edits. A change to the rule
re-points and prunes future occurrences and materialises newly in-range
dates; occurrences that already have sign-ups are kept, and past ones
are frozen.

Content changes need no propagation at all: an occurrence reads its
name, its description and its image through its parent.

## Signing up

Each occurrence has its own public page at `/e/{occurrence-slug}`. A
visitor can book several sessions in one go, and one booking holds one
line item per session. "Every upcoming session" is resolved on the
server, so a stale page cannot book a session that has already started.

The secret link opens that same page in manage mode: change the party
size, the name, or which sessions you are coming to.

## Where it lives

```
backend/services/recurrence.py         the cycle, shared with rosters
backend/services/event_recurrence.py   materialise, reconcile, project
backend/models/events.py               Event, Occurrence, Registration
backend/routers/signups.py             the public writes
frontend/src/pages/EventFormPage.vue   the organiser's editor
frontend/src/public/                   the sign-up page
```
