# Chore rosters

A roster is a recurring set of chores and the volunteers who take turns
doing them. The app decides who does what, keeps the turns fair, and
reminds people the day before.

## What it is

An organiser writes down the chores ("bins out", "bar shift") and how
often the cycle repeats. Volunteers enrol from a public link and tick
the chores they are willing to do. From there the roster runs itself.

There are no accounts. A volunteer gets a secret link to a personal
page, and that link is their identity.

## The cycle

Every roster has a period of `k` weeks. A chore occupies one or more
slots in that cycle: slot `week * 7 + weekday`, so a chore on the
Tuesday of week two of a three-week cycle is slot 8. `k = 1` is a plain
weekly roster.

The cycle anchors on the first Monday on or after `starts_on`. The same
model drives recurring events (`docs/design-recurring-events.md`), and
both read `services/recurrence.py`.

## Three zones in time

* **Committed.** Today to `today + commit_horizon_days`. Shifts exist
  as rows, they are assigned, and they do not move.
* **Projected.** Beyond the horizon. The dates are computed on read, so
  a volunteer can see roughly when their turn comes without the app
  promising it.
* **Past.** Frozen.

The daily tick (`python -m backend.cli roster-tick`) pins the incoming
edge of the horizon: it creates the shifts that just entered it and
assigns them.

## Fairness

Assignment is a virtual clock per volunteer. The lowest clock takes the
next shift, then advances by the share that shift was worth. Somebody
who does more work carries a higher clock and gets skipped until the
others catch up.

The clock is proportional: a volunteer who ticked two of six chores is
expected to do fewer turns than one who ticked all six, and the
arithmetic accounts for it. A volunteer who covers for somebody else
earns a favour, recorded in the ledger, which the next round pays back.

Availability is a set of away ranges per volunteer. An unavailable
volunteer is skipped without their clock moving, so a holiday costs them
nothing and gains them nothing.

`services/chore_assignment.py` is the whole rule, as a pure function
over rows. `services/chore_tick.py` is what calls it.

## What a volunteer can do

From their personal page:

* **Pass.** "I cannot make it." The shift reopens and is reassigned.
* **Claim.** Take an open shift.
* **Cover.** Take somebody else's shift, which earns a favour.
* **Swap.** Trade two confirmed shifts.
* **Leave.** Their address goes, their shifts reopen.

Every one of those writes an event to the ledger, so the roster can
explain how it got where it is.

## Email

One optional address per volunteer, and one switch: reminders on or off.

* Reminders off, or no address given: the address is used once for the
  welcome link and never stored.
* Reminders on: the address is stored encrypted, and the day-before
  reminder decrypts it in the lifecycle worker. Leaving deletes it.

The invariant, checked in the tests: `email_reminders` false implies
`encrypted_email IS NULL`. Reminder mail is part of the paid plan
(`docs/design-paywall.md`); a roster on a free account keeps its
personal pages and its calendar and sends nothing.

## Where it lives

```
backend/models/chores.py            Roster, Chore, Volunteer, Shift, ledger
backend/services/chore_assignment.py  the fairness rule, pure
backend/services/chore_tick.py        the daily tick that applies it
backend/services/chore_projection.py  the beyond-horizon view
backend/routers/chores.py             organiser CRUD
backend/routers/chores_public.py      enrol + the personal page
frontend/src/pages/Chores*.vue        the organiser's side
frontend/src/public_chore/            the volunteer's side
```
