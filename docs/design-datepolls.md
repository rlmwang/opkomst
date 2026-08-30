# Date polls

Pick a date with a group. One link, everybody ticks when they can, the
organiser sees the grid.

## What it is

An organiser picks candidate dates on a calendar, optionally with time
slots inside a day. Everybody else opens one public link and taps the
dates they can make, yes or maybe, with an optional note.

Every date starts blank, and blank means "I can't". There is no fourth
state for saying no: a blank date and an explicit no would tell the
organiser the same thing while sitting in two different places on
disk, which is what made the old four-state pill confusing to fill in.
So a `DatepollResponse` row exists only for a date somebody can make,
and the "can't" count on the organiser's page is the rest of the
respondent pool. Sending no answers at all is a real submission: it
says this person can't do any of the dates.

No accounts, on either side of the link.

## Data

Four tables. A `Datepoll` owns its `DatepollSlot` rows (a date, and
optionally a start and end time). Somebody who answers gets one
`DatepollSubmission` holding their pseudonym, their note and their
secret edit token, with one `DatepollResponse` per slot they can make
(`yes` or `maybe`). A slot they can't make has no row.

The name is optional unless the organiser switched it on, and there is
no email field at all: a date poll never sends mail, so it never asks
for an address.

## Reuse

A date poll is the same shape as an event: an organiser-owned entity
with a slug, a chapter, an image, a bilingual title and description, and
a public page behind a short URL. It inherits the mixins, the archive
and restore behaviour, the QR endpoint, the edit-link contract and the
public page chrome. The parts that are its own are the slots, the
per-slot answers and the month grid the visitor fills in.

## Where it lives

```
backend/models/datepolls.py       the four tables
backend/services/datepolls.py     slots, projections, the grid
backend/routers/datepolls.py      organiser CRUD
backend/routers/datepolls_public.py  the public page and its writes
frontend/src/public_datepoll/     the visitor's page
```
