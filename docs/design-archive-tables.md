# Design: the archive is a separate table

Status: proposed. Nothing below is built yet.

## The problem

Archiving an event, form, datepoll or roster sets `archived_at` and
leaves every row where it was. The live tables therefore hold two kinds
of data: the things an organiser is working on, and everything they have
ever finished. The second kind only grows.

The ceilings in `services/limits.py` bound how many *active* items an
account may have. They do not bound the archive, so a chapter running a
weekly event adds 52 events, their occurrences, their registrations and
their sign-ups every year, for ever, to the same tables every live query
reads.

Nothing is slow today: production holds 4 events and 22 sign-ups. The
shape is the problem, not the size. Every index on `signups` carries
rows nobody will read again, every `WHERE archived_at IS NULL` walks
past them, and every backup copies them.

## What is proposed

Move an archived item, and everything that hangs off it, out of the live
tables and into one archive table. The live tables then contain only
live data, and no query needs `archived_at IS NULL` at all.

```
archived_entities
  id            text        the archived item's own id, kept
  tenant_id     text        NOT NULL, as everywhere
  kind          text        'event' | 'form' | 'datepoll' | 'roster'
  chapter_id    text        nullable, for the list's filter
  name_nl       text        }  what the archive list shows, so the
  name_en       text        }  page never opens the payload
  archived_at   timestamptz }
  starts_on     date        } nullable, kind-specific summary
  participants  integer     } precomputed at archive time
  image_path    text        the image the item still owns
  payload       jsonb       the whole object graph
```

One row per archived item. The columns above the payload are what the
archive page lists and filters on; the payload is everything else, as a
JSON document: the item's own columns plus every child row, keyed by
table name.

### Why one table with a JSON payload

The obvious alternative is a mirror of every table — `events_archive`,
`occurrences_archive`, `signups_archive` and so on. It is worse for one
reason: every future migration has to touch two tables that must stay
identical, and nothing enforces that they do. The mirror rots the first
time somebody adds a column to `signups` and forgets its twin.

A second alternative is Postgres declarative partitioning, splitting each
table on `archived_at IS NULL`. It needs no application code, and the
planner prunes the archived partition automatically. It also requires
the partition key in every primary key, converts a dozen tables, and
leaves the archive in the same tables it was meant to leave. It is the
right answer at a scale this project is nowhere near.

The payload is written once and read on restore. It does not need to be
queryable, so JSON costs nothing here, and it cannot drift from the live
schema because it *is* whatever the live schema was at archive time.

### Restore

`restore` reads the payload, re-inserts the rows in dependency order
with their original ids, and deletes the archive row. Ids are preserved,
so public links and edit links keep working — an archived-then-restored
event is the same event, not a copy.

Three things have to be checked on the way back, because the world moved
while the item was away:

* the chapter may have been deleted, so `chapter_id` is validated the
  same way an update validates it;
* the account's active-item ceiling applies, so a restore into a full
  account is refused with the same message a create would give;
* the tenant must still exist, which the FK enforces anyway.

### What archiving does to children

Everything that cascades today moves with the item: occurrences,
registrations, sign-ups, feedback responses and tokens, form questions
and submissions, datepoll slots and votes, chores, volunteers, shifts.

Two things do not go into the payload:

* **`email_dispatches`** — a dispatch row is work still owed. Archiving
  an item means that work is not going to happen, so the rows are
  deleted and counted failed, exactly as `retire_event_channels` already
  does. Nothing about a queue belongs in an archive.
* **`email_send_counts`** — the totals stay reachable, so they move into
  the payload as plain numbers alongside the summary columns.

### What deleting from the archive does

Deleting an archived item deletes its `archived_entities` row. That is
the whole graph, in one statement, with no cascade to reason about.

It must also delete the image, which is the bug this design is next to:
`crud.hard_delete` removes the row today and leaves the file in the
image repository for ever, and `image_reaper` cannot find it because the
reaper only looks at rows that still exist. With the image path on the
archive row, the delete path has it in hand.

## Order of work

1. **Fix the image leak first**, independently of the rest. It is a
   handful of lines in the four delete routes and it is a real leak
   today. (`services/image.py::delete`, called from `crud.hard_delete`.)
2. `archived_entities` table and its migration.
3. `services/archive.py`: `archive(entity)` and `restore(kind, id)`,
   built on the SQLAlchemy relationship graph so the child list is
   derived rather than hand-written per entity. A hand-written list is
   the same rot as the mirror tables.
4. Move the four archive/restore/delete route pairs onto it.
5. Backfill migration: every row with `archived_at IS NOT NULL` becomes
   an archive row, and leaves the live tables.
6. Drop `archived_at` from the four live models, and the
   `archived_at IS NULL` filters with it. This is the payoff, and it is
   also the point of no return, so it goes last and on its own.

## What this does not solve

* **Registrations and sign-ups of live events** still accumulate for as
  long as the event is live. A recurring event that runs weekly for a
  year is one live row with 52 occurrences and their sign-ups. If that
  becomes a problem the answer is per-occurrence archiving, which this
  design does not preclude.
* **The archive itself grows for ever.** That is the intent. If it ever
  needs bounding, one table partitioned by year is a much easier thing
  to do than what we have now.
* **Deletion requests.** The payload holds display names and party
  sizes, so "delete everything about me" has to reach into it. Today
  that means deleting the archive row; a finer-grained answer would need
  the payload to be searchable, which is the one thing this shape gives
  up.
