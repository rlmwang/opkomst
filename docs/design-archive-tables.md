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
tables and into a mirror of those tables. The live tables then contain
only live data, and no query needs `archived_at IS NULL` at all.

For every table that can hold archived data there is a
`<table>_archive` twin with the same columns. Archiving is

```sql
INSERT INTO signups_archive SELECT * FROM signups WHERE occurrence_id IN (…);
DELETE FROM signups WHERE occurrence_id IN (…);
```

and restoring is the same two statements the other way round.

### The twin is generated, never written

A hand-maintained mirror rots the first time somebody adds a column to
`signups` and forgets its twin. So it is not hand-maintained: each
archive table is derived from the live model at import time.

```python
def mirror(live: Table, metadata: MetaData) -> Table:
    """A copy of the live table with no foreign keys and no indexes:
    these rows point at a world that may not exist any more, and
    nothing queries them until a restore."""
    columns = [
        Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
        for c in live.columns
    ]
    return Table(f"{live.name}_archive", metadata, *columns)
```

One definition, two tables. Alembic autogenerate sees both, so a
migration that adds a column emits the `ALTER` for the live table and
its twin together — they cannot drift, because nobody is asked to
remember.

The twins carry no foreign keys, because an archived sign-up points at
an archived occurrence and neither is in the table the key would
reference. Referential integrity is enforced where rows are live, which
is where it matters, and the restore re-inserts into tables that have
it. They carry no indexes either: nothing reads them except a restore,
which reads by the id it already has.

### Why not a JSON payload

The first draft of this document proposed one archive table holding each
item's whole graph as `jsonb`. It is simpler and it is wrong: a payload
written under today's schema has to be read back under a schema years
newer, and nobody writes migration scripts for blobs. The failure is
silent until somebody restores, and it lands on the person who wanted
their event back.

### Why not partitioning

Splitting each table on an `archived` flag has no drift problem at all —
there is only one schema. It also puts the flag in every primary key,
denormalises it onto every child table, and converts a dozen tables in
one migration. It is the right answer at a scale this project is nowhere
near.

### Restore

`restore` copies the rows back in dependency order — parents before the
children that reference them — with their original ids, and deletes them
from the twins. Ids are preserved, so public links and edit links keep
working: an archived-then-restored event is the same event, not a copy.

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
The set is derived from the relationship graph rather than written out
per entity, for the same reason the twins are generated.

Two things do not move:

* **`email_dispatches`** — a dispatch row is work still owed. Archiving
  an item means that work is not going to happen, so the rows are
  deleted and counted failed, exactly as `retire_event_channels` already
  does. Nothing about a queue belongs in an archive.
* **`email_send_counts`** — the totals stay reachable, so they move to
  their own twin like everything else.

### What deleting from the archive does

Deleting an archived item deletes its rows from the twins, in the same
derived order. There are no cascades here — the twins have no foreign
keys — so the delete walks the same graph the archive did.

It must also delete the image, which is the bug this design sits next
to: `crud.hard_delete` removes the row today and leaves the file in the
image repository for ever, and `image_reaper` cannot find it because it
only looks at rows that still exist. The archived row carries
`image_path` like any other column, so the delete path has it in hand.

## Order of work

1. ~~**Fix the image leak first**~~, done. The image now goes with the
   row that knows its path.
2. ~~The `mirror()` helper and the twins it generates~~, done: 24 tables
   in `backend/models/archive.py`, with a test that fails if a twin's
   columns stop matching its live table.
3. ~~`services/archive.py`~~, done: archive, restore and purge over the
   derived graph.
4. ~~The four archive/restore/delete route pairs~~, done. Two things
   fell out of doing it that the plan had not seen:

   * **`archived_at` needed somewhere to live.** A twin is a mirror and
     cannot carry a column its live table lacks, so the fact of
     archiving is its own small live table, `archive_index`: root,
     entity id, and when. It is what the archive list sorts on.
   * **Archiving twice is a 404 now, not a 409.** The second call looks
     in the live table and the item is not there. Same for restoring
     something that was never archived, and for deleting something not
     yet archived. Each is more truthful than the 409 was.

   And one decision the plan had to make: an in-flight feedback link.
   The token bearer earned the right to answer when the email was sent,
   and tokens last 30 days, so archiving does not revoke them. The
   feedback route reads the live tables and then the archive, and a
   response submitted against an archived event is written into
   `feedback_responses_archive` — the one write the archive takes that is
   not a move. Public pages need no such fallback: `resolve_by_slug`
   already answers 410 for a row it cannot find, which is what an
   archived slug should say anyway.
5. Backfill migration: every row with `archived_at IS NOT NULL`, and its
   children, moves to the twins, with an `archive_index` row each.
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
* **Deletion requests.** The twins hold display names and party sizes,
  so "delete everything about me" has to reach into them. Unlike a JSON
  payload they are ordinary tables, so it is an ordinary `DELETE` with a
  `WHERE` — one of the reasons this shape won.
