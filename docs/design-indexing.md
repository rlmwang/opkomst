# Indexing: what is there, what is missing, what is dead weight

Written after auditing every table against the queries in the code.

## Why production statistics could not answer this

`pg_stat_user_indexes` on the live database reports `idx_scan = 0` for
almost every index. That is not evidence they are useless: the tables
hold a handful of rows each, so Postgres picks a sequential scan every
time and no index gets a chance. At this size the planner is right.

So this audit is analytical. Each index below is judged against the
query shapes in the code, which are what will still be there when the
tables are big enough for the planner to change its mind.

## The floor: every table indexes `tenant_id`

Already true, and not by anyone's diligence — `TenantMixin` declares
`index=True`, so a table cannot carry the column without the index. The
only table without one is `traffic_counts`, which has no `tenant_id` at
all by design (see its module docstring).

## What is missing

**1. The organiser's list pages.** The hottest authenticated read:

```sql
WHERE tenant_id = ? AND chapter_id IN (…) AND archived_at IS NULL
ORDER BY created_at DESC
```

Four tables answer it (`events`, `forms`, `datepolls`, `rosters`), and
none of them has an index that starts where the query starts. What they
have is `(archived_at, chapter_id)`, whose leading column holds two
distinct values — a column with two values cannot narrow anything, so
the index is read as a poor substitute for a scan. The shape that fits
is:

```
(tenant_id, chapter_id, created_at DESC)
```

and for `forms`, which holds three products in one table:

```
(tenant_id, mode, chapter_id, created_at DESC)
```

The ordering column earns its place: with `created_at` in the index the
planner takes the rows in order and stops at the page size, instead of
sorting everything it matched.

**2. The public agenda.** `services/agenda.py` selects occurrences by a
time window across every listed event of a chapter:

```sql
WHERE ends_at >= now AND starts_at <= horizon
```

`occurrences` is indexed on `(event_id, starts_at)`, which serves "the
sessions of this event" and does nothing for "the sessions in this
window". A chapter agenda is a public page and the table grows with
every session of every recurring event, so it wants
`(tenant_id, starts_at)`.

**3. The daily mail cap.** `services/limits.py` sums
`WHERE tenant_id = ? AND day >= ?` over `email_send_counts`, which has
`tenant_id` and `day` as separate indexes. Postgres can combine two
bitmap scans, but `(tenant_id, day)` answers it in one.

## What is dead weight

**Redundant leading columns.** An index on `(a, b)` already serves a
query on `a` alone, so a separate index on `a` is a second copy of the
same information, updated on every write:

| Table | Redundant | Covered by |
|---|---|---|
| `occurrences` | `(event_id)` | `(event_id, starts_at)` |
| `shifts` | `(chore_id)` | `(chore_id, on_date)` |
| `email_dispatches` | `(occurrence_id)` | `(occurrence_id, channel)` |
| `email_send_counts` | `(day)` | `(tenant_id, day)` |

Three more are redundant in exactly the same way — `chapters(tenant_id)`
under `(tenant_id, name)`, `users(tenant_id)` under `(tenant_id, email)`,
`archive_index(tenant_id)` under `(tenant_id, root, archived_at)` — and
they stay. They come from `TenantMixin`, which declares the index with
the column so a table cannot have one without the other. Overriding that
per table trades a structural guarantee for three index updates per
write, which is the wrong way round.

**`created_by` on the four roots.** Nothing filters by it outside
`seed.py`. It is a foreign key, and Postgres does not index those
automatically, but the only reason to index a foreign key is a query
that follows it or a cascade that deletes by it — neither applies here.

**The `archived_at` indexes** (`ix_*_archived_at`, `(archived_at,
chapter_id)`, `(mode, archived_at, chapter_id)`) go when the column
does, in step 6 of `docs/design-archive-tables.md`. They are listed here
so that step does not forget them.

## What is deliberately kept

**`tenant_id` on child tables.** Nothing filters `form_responses` or
`signups` by tenant alone — a child is always reached through its
parent. The index is insurance rather than a query plan: it is what
`tests/test_tenancy.py` leans on, and what makes a "everything of this
tenant" question answerable at all if it is ever asked in an incident.
Roughly twenty small indexes, one extra write each. Cheap now; worth
revisiting if write volume ever becomes the thing that hurts.

**The archive twins have no indexes at all.** Nothing reads them except
a restore, which reads by the id it already holds. See
`docs/design-archive-tables.md`.
